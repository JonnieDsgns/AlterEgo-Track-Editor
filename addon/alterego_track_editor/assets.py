"""Move-only authoring assignment; retain shared mesh and material datablocks."""
import uuid


def move_asset(source, target, root):
    from . import collection_layout
    if source.type != 'MESH' or not source.is_editable:
        raise ValueError('Choose an editable mesh')
    if source.get('tw_project_id') not in (None, root['tw_project_id']):
        raise ValueError('Object belongs to another track project')
    identity = source.get('tw_asset_id')
    if not identity or any(obj != source and obj.get('tw_asset_id') == identity for obj in root.all_objects):
        identity = str(uuid.uuid4())
    world = source.matrix_world.copy()
    collection_layout.move(source, target, root)
    source['tw_asset_id'] = identity
    source['tw_project_id'] = root['tw_project_id']
    source.matrix_world = world
    return source


def terrain_candidate(obj):
    return (obj.type == 'MESH' and bool(obj.get('tw_source_id')) and not obj.get('tw_asset_id')
            and not any(obj.get(key) for key in ('tw_is_marker', 'tw_marker_helper', 'tw_marker_source_only'))
            and obj.get('tw_surface_status') == 'SUGGESTED'
            and obj.tw_surface.collision and obj.tw_surface.surface != 'UNASSIGNED')


def prepare_terrain(context, root, collections):
    context.view_layer.update()
    moved = []
    for source in list(collections['SOURCE'].all_objects):
        if not terrain_candidate(source):
            continue
        asset = move_asset(source, collections['COMMON_TERRAIN'], root)
        asset['tw_export_target'] = 'COMMON_TERRAIN'
        asset['tw_auto_terrain'] = True
        moved.append(asset)
    return moved
