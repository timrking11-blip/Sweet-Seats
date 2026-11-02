---
name: Expo compatibility
description: Avoid relying on older splash configuration examples when scaffolding mobile artifacts.
---

Validate a newly scaffolded Expo companion with both the dependency checker and Expo Doctor before delivery. Do not assume the scaffold or older skill examples match the installed SDK's config schema.

**Why:** The mobile scaffold had minor native dependency mismatches, and the installed SDK rejected the older top-level splash configuration even though the skill example recommended it.

**How to apply:** Use the installed SDK's splash plugin configuration and dependency alignment tools; retain the scaffold's managed login step.
