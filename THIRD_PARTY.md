# Source and dependency notices

The project is distributed under AGPL-3.0-or-later; see LICENSE. Component notices remain applicable.

- Owner-authorized Track Workshop 0.10.1 Python source, authored by Yannick, forms the baseline. Original hashes: docs/research/baseline-source.json. Native/.NET backends are excluded.
- Bundled native readers derive from TrackView 0.4.0 and upstream codecs. Original hashes/provenance: docs/research/native-source.json. TrackView identifies AGPL-3.0-or-later. The complete upstream Swofty license/notices are retained in addon/alterego_track_editor/licenses/Swofty-AGPL.txt; project AGPL text is also bundled.
- Blender supplies bpy, mathutils and NumPy. Pillow is optional for additional image decoding; the bounded included preview codec handles common BC/RGBA formats without it.
- SwoftyLauncher package contracts were inspected; no launcher executable/backend is shipped or invoked.
- Simplified Track Manager, F1 Track Cameras and EgoEngineLibrary were reviewed as references; review component notices before further code integration.

Source licenses do not grant redistribution rights to game textures, models, sounds, proprietary shaders or third-party tracks. No such assets are included. Public template packs require separate asset provenance and permissions.
