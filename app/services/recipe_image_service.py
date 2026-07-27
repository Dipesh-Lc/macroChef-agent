"""Recipe imagery.

ROADMAP 4.4 quick fix removed this module's old `placeholder_image_url`
helper, which built a `placehold.co` URL (a remote network call per card,
with the recipe title baked into the served image as text that clipped on
long titles). Cards with no real `image_url`/`image_path` now render
zero-network deterministic local art client-side instead -- see
`web/src/components/RecipeArt.tsx` and `web/src/lib/placeholderImage.ts`.

This module is the reserved home for ROADMAP 4.4's **[STRETCH]** item: an
offline image-generation service that renders one real image per
base-corpus recipe via a paid image API (human cost-approval gate
required first), stores it under `data/library/images/`, and serves it as
a static file -- never generated at request time. Not implemented yet.
"""
