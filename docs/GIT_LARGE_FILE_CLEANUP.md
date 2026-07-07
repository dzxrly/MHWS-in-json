# Git Large File Cleanup

GitHub rejects pushes containing files larger than 100 MB anywhere in branch history.

This repository ignores new Stage VoxelData and Enemy Constraint JSON files, but existing commits may still contain those blobs. A normal deletion commit is not enough; the affected blobs must be removed from history before pushing.

The cleanup should remove these tracked path groups from Git history:

- `MHWS-in-json/natives/STM/GameDesign/Stage/**/VoxelData/`
- `MHWS-in-json/natives/STM/GameDesign/Stage/**/*VoxelData*.json`
- `MHWS-in-json/natives/STM/GameDesign/Enemy/**/Data/*Constraint*.json`

This is a history rewrite and should only be run after confirming that rewriting local branch history is acceptable.
