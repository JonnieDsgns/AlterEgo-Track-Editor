"""Native race routes and track markup (TrackSpace/TM/AISplineData) for preview and markup edits.

Geometry (spline knots, AI gates, volumes) is read for display only. Track markup
intervals are fractions along a named TrackSpace spline; editing them changes only
those Start/End attributes. Positions shown along a spline assume arc length over
the knot polyline (closed splines include the closing segment): the game's exact
parameterization is not established, so displayed positions are approximate while
the stored fractions are exact.
"""
import bisect
import math
from .native.formats.bxml import Document, FormatError, floats

# Markup that drives timing, rules and race systems; other types are preserved untouched.
GAMEPLAY = ('sector_1', 'sector_2', 'sector_3', 'spd_trp', 'tt_invalidate_lap', 'drs_det', 'drs_act',
            'ers_over_det', 'ers_over_act', 'x_mode', 'pit_lim_on', 'pit_lane_entry_zone', 'pitlane_exit_zone',
            'show_pitstop_zone', 'pit_ent_osd', 'grid_park_osd', 'pit_sc_exempt', 'ai_pit_trigger', 'plr_pit_trgr',
            'first_corner_zone', 'illegal_overtake_distance', 'rolling_start_zone', 'safety_car_main', 'safety_car_pit',
            'safety_car_player_control_countdown', 'ai_flying_lap_trigger', 'pit_ai_yield')
SECTORS = ('sector_1', 'sector_2', 'sector_3')


def fraction_text(value):
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError('Markup positions must be fractions from 0 to 1')
    text = f'{value:.6f}'.rstrip('0').rstrip('.')
    return text or '0'


class Spline:
    def __init__(self, name, points, closed):
        if len(points) < 2:
            raise ValueError('Spline has fewer than two knots: '+name)
        self.name, self.points, self.closed = name, points, closed
        path = points + [points[0]] if closed else points
        self.cumulative = [0.0]
        for a, b in zip(path, path[1:]):
            self.cumulative.append(self.cumulative[-1] + math.dist(a, b))
        self.length = self.cumulative[-1]
        self.path = path
        if self.length <= 0:
            raise ValueError('Degenerate spline: '+name)

    def point(self, fraction):
        distance = min(max(fraction, 0.0), 1.0) * self.length
        i = min(max(bisect.bisect_right(self.cumulative, distance) - 1, 0), len(self.path) - 2)
        span = self.cumulative[i + 1] - self.cumulative[i]
        u = 0.0 if span <= 0 else (distance - self.cumulative[i]) / span
        a, b = self.path[i], self.path[i + 1]
        return [a[k] + (b[k] - a[k]) * u for k in range(3)]

    def segment(self, start, end, step=4.0):
        """Points from start to end; an interval with start > end wraps through 1/0 on closed splines."""
        if start > end and not self.closed:
            raise ValueError('Only closed splines can wrap: '+self.name)
        stop = end + 1.0 if start > end else end
        count = max(2, int((stop - start) * self.length / step) + 2)
        fractions = [start + (stop - start) * i / (count - 1) for i in range(count)]
        return [self.point(f - 1.0 if f > 1.0 else f) for f in fractions]

    def nearest(self, point):
        """Fraction of the closest point on the polyline (approximate parameterization)."""
        best = (math.inf, 0.0)
        for i, (a, b) in enumerate(zip(self.path, self.path[1:])):
            ab = [b[k] - a[k] for k in range(3)]
            denominator = sum(v * v for v in ab)
            u = 0.0 if denominator == 0 else max(0.0, min(1.0, sum((point[k] - a[k]) * ab[k] for k in range(3)) / denominator))
            q = [a[k] + ab[k] * u for k in range(3)]
            distance = math.dist(q, point)
            if distance < best[0]:
                best = (distance, (self.cumulative[i] + u * (self.cumulative[i + 1] - self.cumulative[i])) / self.length)
        return min(best[1], 1.0), best[0]


class RouteData:
    """Route resources of one track namespace, located by native resource type."""

    def __init__(self, catalog, code):
        found = {}
        for uri, (_, resource) in catalog.by_uri.items():
            if resource.type_name in ('TrackSpace', 'TS', 'TM', 'AISplineData') and f'/tracks/{code}/' in uri:
                found.setdefault(resource.type_name, []).append(uri)
        for kind in ('TrackSpace', 'TM'):
            if len(found.get(kind, [])) != 1:
                raise ValueError(f'Expected one {kind} resource for {code}, found {len(found.get(kind, []))}')
        self.uris = {k: v[0] for k, v in found.items() if len(v) == 1}
        self.catalog = catalog
        self.tm_raw = catalog.read(self.uris['TM'])
        self.tm = Document(self.tm_raw)
        closed = {}
        if 'TS' in self.uris:
            for volume in Document(catalog.read(self.uris['TS'])).root.elements('VolumeList'):
                closed[volume.get('type')] = volume.get('closed') == 'True'
        self.splines = {}
        for spline in Document(catalog.read(self.uris['TrackSpace'])).root.elements('TrackSpaceSpline'):
            name = spline.get('name')
            points = [floats(k.get('position')) for k in spline.elements('Knot')]
            self.splines[name] = Spline(name, points, closed.get('main', True) if name == 'maintrack' else False)
        self.markup = []
        lists = self.tm.root.elements('MarkupList')
        if len(lists) != 1:
            raise ValueError('Unexpected track markup layout')
        for index, element in enumerate(lists[0].elements('MarkupElement')):
            attributes = element.elements('Attributes')
            types = [a.get('Type') for a in attributes[0].elements('Attribute')] if attributes else []
            props = {}
            for attribute in attributes[0].elements('Attribute') if attributes else []:
                for properties in attribute.elements('Properties'):
                    for prop in properties.elements('Property'):
                        props[attribute.get('Type')+'.'+prop.get('Type')] = prop.get('Value')
            self.markup.append({'index': index, 'name': element.get('Name'), 'spline': element.get('SplineName'),
                                'start': float(element.get('Start')), 'end': float(element.get('End')),
                                'types': types, 'props': props, 'gameplay': any(t in GAMEPLAY for t in types)})
        self.ai = None
        if 'AISplineData' in self.uris:
            self.ai = self._ai(Document(catalog.read(self.uris['AISplineData'])).root)

    @staticmethod
    def _ai(track):
        gates = []
        for gate in track.elements('gates')[0].elements('gate'):
            position = floats(' '.join(gate.elements('position')[0].get(k) for k in 'xyz'))
            normal = floats(' '.join(gate.elements('normal')[0].get(k) for k in 'xyz'))
            offsets = {w.get('type'): float(w.get('length')) for w in gate.elements('waypoints')[0].elements('waypoint')}
            gates.append({'id': int(gate.get('id')), 'name': gate.get('name'), 'position': position, 'normal': normal, 'offsets': offsets})
        routes = [{k.decode(): v.decode() for k, v in r.attrs} for r in track.elements('routes')[0].elements('route')]
        links = {int(l.get('id')): (int(l.get('from_gate')), int(l.get('to_gate'))) for l in track.elements('links')[0].elements('link')}
        return {'gates': gates, 'routes': routes, 'links': links}

    def ai_line(self, route_type, waypoint):
        """Ordered points of one waypoint type along a route's link chain (position + normal * signed length)."""
        route = next(r for r in self.ai['routes'] if r['type'] == route_type)
        by_id = {g['id']: g for g in self.ai['gates']}
        ids = []
        for link in range(int(route['from_link']), int(route['to_link']) + 1):
            if link not in self.ai['links']:
                continue
            a, b = self.ai['links'][link]
            for gate in (a, b):
                if not ids or ids[-1] != gate:
                    ids.append(gate)
        points = []
        for gate_id in ids:
            gate = by_id[gate_id]
            if waypoint in gate['offsets']:
                length = gate['offsets'][waypoint]
                points.append([gate['position'][k] + gate['normal'][k] * length for k in range(3)])
        return points

    def write_markup(self, edits):
        """Return new TM bytes changing only Start/End of the given elements {index: (start, end)}."""
        if not edits:
            return self.tm_raw
        document = Document(self.tm_raw)
        elements = document.root.elements('MarkupList')[0].elements('MarkupElement')
        values = {m['index']: (m['start'], m['end']) for m in self.markup}
        for index, (start, end) in edits.items():
            row = self.markup[index]
            if not row['gameplay']:
                raise ValueError('Only gameplay markup intervals are editable: '+row['name'])
            spline = self.splines.get(row['spline'])
            if spline is None:
                raise ValueError('Markup references a missing spline: '+row['name'])
            start_text, end_text = fraction_text(start), fraction_text(end)
            if float(start_text) > float(end_text) and not spline.closed:
                raise ValueError('Only closed splines can wrap past 1: '+row['name'])
            if 'sector_1' in row['types'] and float(start_text) != row['start'] or 'sector_3' in row['types'] and float(end_text) != row['end']:
                raise ValueError('The lap start (sector 1 start / sector 3 end) is fixed; move sector boundaries only')
            element = elements[index]
            if (start_text, end_text) != (element.get('Start'), element.get('End')):
                element.set('Start', start_text)
                element.set('End', end_text)
            values[index] = (float(start_text), float(end_text))
        sectors = {t: values[m['index']] for m in self.markup for t in m['types'] if t in SECTORS}
        if len(sectors) == 3 and (sectors['sector_1'][1] != sectors['sector_2'][0] or sectors['sector_2'][1] != sectors['sector_3'][0]):
            raise ValueError('Sector boundaries must stay chained: sector 1 end = sector 2 start, sector 2 end = sector 3 start')
        if len(sectors) == 3 and not sectors['sector_1'][0] < sectors['sector_1'][1] < sectors['sector_2'][1] < sectors['sector_3'][1]:
            raise ValueError('Sectors must stay in lap order')
        data = document.to_bytes()
        self._verify(data, {i: (fraction_text(s), fraction_text(e)) for i, (s, e) in edits.items()})
        return data

    def _verify(self, data, edits):
        # Independent decode of the whole tree: only edited Start/End attributes may differ.
        old = Document(self.tm_raw).root
        new = Document(data).root
        targets = {id(e): edits[i] for i, e in enumerate(old.elements('MarkupList')[0].elements('MarkupElement')) if i in edits}

        def same(a, b):
            if type(a) is not type(b):
                raise FormatError('Markup structure changed')
            if not hasattr(a, 'attrs'):
                if a.raw != b.raw:
                    raise FormatError('Markup text changed')
                return
            expected = [[k, v] for k, v in a.attrs]
            if id(a) in targets:
                for pair in expected:
                    if pair[0] in (b'Start', b'End'):
                        pair[1] = targets[id(a)][pair[0] == b'End'].encode()
            if a.name != b.name or expected != b.attrs or a.close != b.close or len(a.children) != len(b.children):
                raise FormatError('Markup readback failed: '+a.tag)
            for x, y in zip(a.children, b.children):
                same(x, y)

        same(old, new)


# Stock envelope (28 installed tracks), widened slightly: DRS activation 338-1039 m, detection
# 108-1938 m before it, X-Mode 155-1748 m.
DRS_ACTIVATION, DRS_GAP, X_MODE = (300, 1100), (50, 2000), (150, 1800)


def interval_metres(spline, start, end):
    """Length of an interval along a spline; start > end wraps through the lap line."""
    span = end - start if end >= start else 1.0 - start + end
    return span * spline.length


def zone_warnings(rows, splines):
    """Warnings for DRS and Straight Mode (X-Mode) zones outside the envelope of the 28 stock tracks.

    Measured stock ranges (docs/research/routes-markup.md): DRS activation 338-1039 m, detection
    108-1938 m before activation, X-Mode zones 155-1748 m; activation zones of different IDs and
    Full X-Mode zones never overlap. The F1MapEditor catalogue ranges (300-1000, 50-600, 180-1750)
    flag 18 stock zones, so they are not used. Warnings only: the game's limits are not known.
    """
    main = splines.get('maintrack')
    if main is None:
        return []
    def zones(kind):
        return [r for r in rows if kind in r['types'] and r['spline'] == 'maintrack']
    def overlap(a, b):
        def parts(r):
            return [(r['start'], r['end'])] if r['end'] >= r['start'] else [(r['start'], 1.0), (0.0, r['end'])]
        return any(x0 < y1 and y0 < x1 for x0, x1 in parts(a) for y0, y1 in parts(b))
    warnings = []
    detections = {r['props'].get('drs_det.ID'): r for r in zones('drs_det')}
    activations = zones('drs_act')
    for act in activations:
        length = interval_metres(main, act['start'], act['end'])
        if not DRS_ACTIVATION[0] <= length <= DRS_ACTIVATION[1]:
            warnings.append(f"{act['name']}: DRS activation {length:.0f} m (stock {DRS_ACTIVATION[0]}-{DRS_ACTIVATION[1]} m)")
        det = detections.get(act['props'].get('drs_act.ID'))
        if det is None:
            warnings.append(f"{act['name']}: no DRS detection with the same ID")
        else:
            gap = interval_metres(main, det['end'], act['start'])
            if not DRS_GAP[0] <= gap <= DRS_GAP[1]:
                warnings.append(f"{act['name']}: detection {gap:.0f} m before activation (stock {DRS_GAP[0]}-{DRS_GAP[1]} m)")
    for i, a in enumerate(activations):
        for b in activations[i + 1:]:
            if overlap(a, b):
                warnings.append(f"{a['name']} overlaps {b['name']}")
    modes = zones('x_mode')
    for zone in modes:
        length = interval_metres(main, zone['start'], zone['end'])
        if not X_MODE[0] <= length <= X_MODE[1]:
            warnings.append(f"{zone['name']}: Straight Mode zone {length:.0f} m (stock {X_MODE[0]}-{X_MODE[1]} m)")
    full = [z for z in modes if z['props'].get('x_mode.type') == 'Full']
    for i, a in enumerate(full):
        for b in full[i + 1:]:
            if overlap(a, b):
                warnings.append(f"{a['name']} overlaps {b['name']}")
    return warnings
