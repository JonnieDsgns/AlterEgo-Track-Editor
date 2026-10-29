# Source and dependency notices

This repository now includes owner-authorized Track Workshop 0.10.1 Python source and synthetic test fixtures, with original author attribution and baseline hashes. It excludes the packaged native backend/runtime and game-derived assets. The general project distribution license and component notice closure remain documented integration tasks; no upstream license is replaced by this document.

Sources reviewed:

- Track Workshop 0.10.1 and the supplied AlterEgo/Tracktool source: baseline Blender tools and native track services. Preserve provenance; exact backend source identity and root license metadata require closure.
- TrackView 0.4: native track/model/material reader and exporter. Identifies AGPL-3.0-or-later.
- F1 Track Cameras 0.1.1: camera, spline and activation editing. Local project carries MIT notices; constituent codecs retain their own provenance.
- [SwoftyLauncher](https://github.com/Swofty-Developments/SwoftyLauncher): package contracts and launcher responsibilities. Carries AGPL notices, with component exceptions documented upstream.
- [Simplified Track Manager](https://github.com/TeamSimplified/simplified-suite/tree/main/Simplified%20Track%20Manager): metadata and addon packaging reference. Suite root has GPLv3 license text; review component/dependency notices before code reuse.
- [EgoEngineLibrary](https://github.com/EgoEngineModding/Ego-Engine-Modding): native low-level format library, with MIT notice in the inspected vendored source.

Package-specific licenses and runtime redistribution requirements must be inventoried before integration. Source licenses do not grant redistribution rights to game textures, models, sounds, proprietary shader payloads or third-party track content. Public template packs require their own asset provenance and permission records.
