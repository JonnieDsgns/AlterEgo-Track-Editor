"""Native world keys are distinct from database dataset names and UI labels."""
CORE = {
    'common': ('COMMON_OBJECTS', 'Common'),
    'f1': ('2025_F1', 'F1 2025'),
    'f1_myteam': ('2025_MYTEAM', 'MyTeam 2025'),
    'f2': ('2025_F2', 'F2 2025'),
    'f1_26': ('2026_F1', 'F1 2026'),
    'f1_26_myteam': ('2026_MYTEAM', 'MyTeam 2026'),
    'f2_26': ('2026_F2', 'F2 2026'),
    'classic': ('CLASSIC', 'Classic'),
    'f1_previous_myteam': ('NATIVE_f1_previous_myteam', 'Previous MyTeam'),
    'f1_story': ('NATIVE_f1_story', 'Story'),
    'f1_previous_story': ('NATIVE_f1_previous_story', 'Previous Story'),
}
REQUIRED = ('f1', 'f1_myteam', 'f2', 'f1_26', 'f1_26_myteam', 'f2_26', 'classic')


def role(key):
    return CORE.get(key, ('NATIVE_' + key, 'Native variant: ' + key))


def inventory(world_keys):
    keys = sorted(set(world_keys))
    return {'core_required':list(REQUIRED),'release_ready':False,'present': keys, 'missing': [k for k in REQUIRED if k not in keys],
            'additional': [k for k in keys if k not in REQUIRED and k != 'common']}
