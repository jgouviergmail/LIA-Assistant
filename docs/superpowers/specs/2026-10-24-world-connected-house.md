# Connected house revision

This revision supersedes the spatial and colour direction in [the readable campus specification](2026-10-24-world-readable-campus.md). The owner rejected that iteration: distant buildings, oversized rooms, sparse furnishing and desaturated colours were not acceptable. Its functional contracts remain applicable.

## Experience and composition

The main location is one connected house, seen in an isometric cutaway. Adjacent rooms group related activities. A central meeting hall connects the post office, creative studio and social lounge; the library, writing room, connected workshop and planning room form the quieter rear wing. Full-height rear walls frame the composition. Low internal partitions maintain sightlines and contain real door openings.

The radio lives on a furnished outdoor terrace. The greenhouse and observatory are close to the main entrance; the observatory remains exposed to local weather. A planted fountain garden connects them. The personal retreat is nearby but separate. The world still scrolls and zooms; fitting everything on screen is not an acceptance criterion.

Furnishing is placed as usable clusters: desk and correctly facing chair, reading table and library, conversation sofas and coffee table, radio and shaded outdoor seating. Passageways and every pose approach remain clear. The functional object's semantic identity survives relocation.

## Art direction

Warm timber, cream masonry, more distinct teal, coral and violet textiles, green foliage and pink blossom replace the greyed palette. Shared walls have continuous joined bodies and caps. Thin furniture parts, shelves, glazing and contact shadows remain readable at gameplay zoom.

The garden has different tree silhouettes, small flowers and shaded seating. Fountain jets, subtle screen activity and a bounded number of blossom petals add life. Reduced motion suppresses decorative motion. Night uses multiplicative colour shading so its darkening does not create an opaque blue veil; weather remains local and never appears through authored shelter.

## Implementation boundaries

- Authored local room furniture is translated to world coordinates by one typed helper.
- One wall-run compiler deduplicates junctions and respects openings. The painter consumes the same connection mask, which participates in texture identity.
- The same authored scene compiles the server collision and pose catalogue. Geometry changes increment scene version; old movement state cannot inhabit the new map.
- Native activity dispatch, privacy, authority, message delivery, translation limits and private home decoration retain their existing paths.
- No LLM call, personal content or provider request is added for decoration or navigation.
- Placement and privacy tests use semantic anchors rather than stale absolute coordinates.
- Qualification uses owned local preview infrastructure. Main, other worktrees and shared Docker resources remain untouched.

## Acceptance evidence required

Automated checks must cover connected room journeys, blocking-object separation, every activity and seat approach, wall junction contours and texture ownership, server catalogue parity, private-home projection, existing world unit tests and applicable quality ratchets.

Browser review must cover the ordinary gameplay view, close architectural details, all themed areas, mobile framing and navigation, direct object discovery, seating, private home behaviour and two-person message delivery. Check real console errors separately from expected unauthenticated responses in the unconnected art preview. Reduced-motion, night and weather views must remain usable. Physical Raspberry Pi and phone performance remain a distinct qualification step.

## Reference study

The owner supplied [MalinosLand](https://github.com/Rogue06/MalinosLand). Its [world design](https://github.com/Rogue06/MalinosLand/blob/main/docs/WORLD_DESIGN.md), [art direction](https://github.com/Rogue06/MalinosLand/blob/main/docs/ART_DIRECTION.md) and [interaction principles](https://github.com/Rogue06/MalinosLand/blob/main/docs/GAME_DESIGN.md) informed this revision: contiguous rooms, low foreground partitions, activity clusters, recognisable objects and contextual interaction. The implementation and artwork here are authored for LIA; no source code or graphic asset was copied from that project.
