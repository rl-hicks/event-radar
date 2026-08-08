# Event Radar North Bay Hiking Catalog — Research and Curation Audit

**Catalog version:** 2026-08-07  
**Baseline:** Santa Rosa, California  
**Final inventory:** 35 routes  
**Research scope:** Stable route characteristics only; current closures, alerts, fire restrictions, weather, tides, parking availability, and temporary access rules remain runtime data.

## Executive finding

This catalog is ready for a coding handoff as a compact decision set, not as an exhaustive trail directory. It deliberately spans low-friction local walks, shaded redwood options, exposed cool-season hills, coastal wind-sensitive routes, moderate half-days, and demanding destination objectives. Every record identifies a specific route and start point, contains a trailhead coordinate, links to an official or land-manager source, and separates directly sourced facts from recommendation judgments.

The strongest remaining limitation is route-metric standardization. Eighteen records have high overall research confidence and 17 have moderate confidence; none are marked low. The moderate records are retained because they add decision value, but their exact gain, route endpoint, or route-variant issue is visible in both this audit and the JSON.

## Stage 1 — Final schema audit

### Stable/dynamic boundary

The catalog stores stable facts and durable judgments: route identity, start coordinates, distance, gain, duration range, terrain, shade/exposure, weather sensitivities, broad seasonal fit, access baseline, and recurring constraints. It does **not** state that a trail is currently open, quote current parking prices as permanent facts, or encode current fire, storm, tide, bridge, reservation-availability, or wildlife restrictions.

Every record has `dynamic_status_check_required: true`. That is intentional: even a normally reliable urban loop can have a storm closure, while remote coastal and mountain routes need substantially more runtime validation.

### Final record shape

| Group | Fields | Purpose |
|---|---|---|
| Identity | `id`, `name`, `park_or_area`, `managing_agency`, `region`, `nearest_city` | Stable route and ownership identity |
| Trailhead | `trailhead_name`, `latitude`, `longitude`, `coordinate_precision` | Coordinate-based weather and navigation handoff |
| Sources | `official_source_url`, `secondary_source_urls` | Auditable factual foundation |
| Route | `route_type`, `route_start`, `route_end`, `trail_sequence` | Prevents different route variants from being merged |
| Effort | `distance_miles`, `elevation_gain_ft`, `estimated_duration_minutes`, `difficulty` | Deterministic effort and daylight reasoning |
| Environment | `setting`, `shade`, `exposure` | Stable terrain and microclimate interpretation |
| Weather response | `heat_sensitivity`, `wind_sensitivity`, `mud_sensitivity`, `rain_sensitivity` | Converts forecast conditions into route-specific meaning |
| Season/timing | `preferred_months`, `acceptable_months`, `poor_months`, `best_time_of_day`, `minimum_reasonable_daylight_minutes` | Broad climatological fit and scheduling constraints |
| Recommendation | `solo_fit`, `scenic_value`, `experience_tags`, `drive_friction_from_santa_rosa` | Candidate diversity and synthesis features |
| Access/notes | `parking_notes`, `access_baseline_notes`, `seasonal_access_notes`, `important_route_notes` | Stable access expectations and route caveats |
| Provenance/quality | `provenance`, `data_quality`, `dynamic_status_check_required` | Direct versus inferred facts, confidence, and uncertainty |

### Meaningful schema improvements

1. **Route identity is explicit.** `route_start`, `route_end`, and `trail_sequence` stop a park-level page or a nearby loop from silently becoming the selected route.
2. **Duration is a numeric range.** `estimated_duration_minutes.min/max` is more honest and useful than a single pseudo-precise time.
3. **Coordinates have precision metadata.** A mapped trailhead and an approximate location inside a small parking area are distinguishable.
4. **Access is split by time horizon.** Stable parking/access expectations and recurring seasonal behavior live in the catalog; current status remains a runtime lookup.
5. **Judgment is first-class provenance.** Each record lists directly sourced and derived fields, the derivation basis, source notes, confidence, and uncertainties.
6. **Drive friction is explicit but coarse.** `very_close`, `regional`, and `destination` avoid pretending traffic creates a stable minute estimate.
7. **Seasonal fit partitions all twelve months.** The month lists are broad North Bay climatology judgments, not closures or guarantees; weather and access still override them.

## Stage 2 — Broad candidate inventory

The broad pass considered **59 routes**. Thirty-five were selected and 24 excluded before full record research. “Excluded” does not mean poor; it means redundant, weakly standardized, or insufficiently valuable relative to drive and catalog coverage.

| Geography | Selected candidates | Excluded candidates | Pool |
|---|---|---|---:|
| Santa Rosa core | Spring Lake Loop; Annadel Canyon–Spring Creek; Taylor summit; Taylor Colgan Creek; Crane Creek short loop | Annadel Central Loop; Warren Richardson–Lake Ilsanjo; Laguna de Santa Rosa Trail | 8 |
| North Sonoma / Russian River | Shiloh Creekside–Big Leaf; Foothill Alta Vista; Riverfront Lake Trail; North Sonoma Mountain Ridge; Jack London Sonoma Ridge; Armstrong Pioneer; Armstrong East–Pool Ridge | Healdsburg Ridge; Fitch Mountain; Jack London Ancient Redwood; Monte Rio Redwoods; Lake Sonoma Southlake routes | 12 |
| Sonoma Valley / Mayacamas | Sonoma Overlook Upper Loop; Sugarloaf Bald Mountain; Sugarloaf Pony Gate–Canyon; Hood Mountain–Gunsight Rock | Sugarloaf Vista Trail; Hood Mountain from Lawson/Los Alamos | 6 |
| Petaluma / south Sonoma | Helen Putnam Ridge–South; Tolay Bay View Vista | Helen Putnam Panorama variant; Tolay short lake loop | 4 |
| Sonoma Coast | Bodega Head; Kortum; Pomo Canyon; Jenner Coastal Prairie; Salt Point coast; Salt Point Pygmy Forest; Kruse Rhododendron | Jenner Sea-to-Sky; Sea Ranch Bluff Top; Stillwater Cove; Pinnacle Gulch; Doran Bird Walk | 12 |
| Marin / Mount Tam | Steep Ravine–Matt Davis; Cataract loop; Muir Woods Ben Johnson–Dipsea; Tennessee Valley | Muir Woods Main Trail; Mount Tam East Peak via Railroad Grade; Miwok–Wolf Ridge | 7 |
| Point Reyes | Tomales Point; Chimney Rock; Abbotts Lagoon; Alamere Falls | Bear Valley/Arch Rock family; Point Reyes Lighthouse walk | 6 |
| Napa side | Bothe Coyote Peak; Mount St. Helena | Skyline–Lake Marie; Moore Creek/Valentine Vista | 4 |

## A. Catalog overview

### Coverage

| Dimension | Distribution |
|---|---|
| Difficulty | 10 easy · 12 moderate · 13 hard |
| Time commitment | 12 with a maximum estimate of 2 hours · 13 in the 2–4 hour band · 10 half-day or longer |
| Drive friction | 5 very close · 17 regional · 13 destination |
| Shade | 9 high · 10 moderate · 16 low |
| Heat sensitivity | 15 low · 11 moderate · 9 high |
| Wind sensitivity | 11 low · 11 moderate · 13 high |
| Mud sensitivity | 4 low · 18 moderate · 13 high |
| Research confidence | 18 high · 17 moderate · 0 low |

Setting tags overlap by design. The 35 records contain 18 forest, 17 grassland, 16 ridge, 14 creek, 11 coastal, 9 mountain, 9 redwood, 6 lake, 6 oak-woodland, 5 bluff, 4 beach, and 3 waterfall tags, plus singular wetland, lagoon, pygmy-forest, botanical, rocky-shore, and volcanic experiences.

### Weather and season diversity

- **Hot-weather resilience:** Riverfront Lake Trail, both Armstrong routes, Kruse Rhododendron, Mount Tam Cataract, Muir Woods, and several coastal routes provide shade or maritime cooling.
- **Cool-weather exposed choices:** Taylor Mountain, Crane Creek, Foothill, Helen Putnam, Tolay, Sonoma Overlook, Sugarloaf Bald Mountain, and Mount St. Helena reward cool, dry forecasts.
- **Rain-payoff choices with rain limits:** Sugarloaf's waterfall loop, Mount Tam Cataract, Steep Ravine, and Alamere gain scenic value from seasonal water, but heavy rain can make them unsuitable. Rain sensitivity is therefore high even when the post-rain payoff is high.
- **Wind-sensitive alternatives:** Eleven coastal/headland routes are intentionally marked for strong wind screening; inland forest routes offer counter-programming.
- **Low-friction spontaneity:** Spring Lake, two Taylor routes, Annadel, and Crane Creek can fill short Santa Rosa availability windows without turning the catalog into a list of neighborhood strolls.

### Major strengths

- A useful **effort ladder** within the same home region, from Spring Lake and Colgan Creek to Hood Mountain.
- Real **microclimate diversity**, with old-growth redwoods, oak woodland, open ranchlands, coastal bluffs, creek canyons, and mountain summits.
- Several **experience anchors** that justify recommendation on identity, not just mileage: tule elk at Tomales Point, pygmy forest at Salt Point, seasonal rhododendrons at Kruse, old-growth redwoods at Armstrong/Muir Woods, and volcanic high-country views at Mount St. Helena.
- Explicit **route variation control** in parks where casual sources routinely mix distances.

### Remaining blind spots

- The catalog is light on accessible unpaved routes; Spring Lake and Armstrong Pioneer are the strongest broadly accessible records.
- Lake Sonoma and Healdsburg-area hiking remains underrepresented because authoritative route-specific metrics were weaker than for selected alternatives.
- There is no tide table, fire-risk model, recent-rain history, or closure feed here; those belong in runtime systems.
- Trailhead coordinates are catalog-grade, not survey-grade. Two are marked `approximate_trailhead`; all should be checked against the application's mapping provider before production release.

## B. Final hike inventory

Legend: **S/E** = shade/exposure. Sensitivities are ordered **heat / wind / mud / rain**. “Best” months are broad climatological guidance, not access guarantees.

### Santa Rosa and close-in Sonoma County

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Spring Lake Loop | 2.3 mi · ~50 ft · 45–75 min · easy | Lake/creek; S moderate / E moderate; moderate / low / low / low | Flexible all-year low-friction outing; gain is estimated | [Sonoma County Regional Parks](https://parks.sonomacounty.ca.gov/visit/find-a-park/spring-lake-regional-park) |
| Canyon–Spring Creek Loop | 7.4 mi · 629 ft · 3–4 hr · moderate | Forest/lake/creek; S moderate / E moderate; moderate / low / moderate / moderate | Annadel half-day classic; best Feb–May and Oct–Nov | [California State Parks route page](https://www.parks.ca.gov/?page_id=31891) |
| Taylor Mountain Summit | ~4.0 mi · 1,067 ft · 2–3 hr · hard | Grassland/ridge; S low / E high; high / high / high / high | Local workout and golden-hour views; minor junction variation | [Sonoma County peak guide](https://parks.sonomacounty.ca.gov/learn/blog/conquer-sonoma-countys-peaks-5-challenging-trails-with-stunning-views) |
| Colgan Creek Loop | 1.3 mi · 140 ft · 35–60 min · easy | Creek/oak woodland; S moderate / E moderate; moderate / low / moderate / moderate | Short Taylor alternative with newer trail mapping | [Sonoma County route feature](https://parks.sonomacounty.ca.gov/learn/blog/three-trails-that-make-taylor-mountain-feel-like-a-whole-new-park) |
| Crane Creek Short Loop | 1.4 mi · ~180 ft · 35–60 min · easy | Grassland/oaks; S low / E high; high / moderate / high / high | Wildflower and birding sampler; gain estimated | [Sonoma County route feature](https://parks.sonomacounty.ca.gov/learn/blog/explore-oak-woodlands-and-wildflowers-at-crane-creek-regional-park) |

### North Sonoma, Russian River, and Sonoma Mountain

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Creekside–Big Leaf Loop | 3.8 mi · 600 ft · 1h40–2h30 · moderate | Oak woodland/creek/ridge; S moderate / E moderate; moderate / moderate / high / high | Quiet mixed-terrain loop; exact metrics rely on a route-specific secondary trace | [Shiloh Ranch official page](https://parks.sonomacounty.ca.gov/visit/find-a-park/shiloh-ranch-regional-park) |
| Alta Vista–Three Lakes Loop | ~3.0 mi · 600 ft · 1h30–2h15 · moderate | Grassland/lakes/ridge; S low / E high; high / moderate / high / high | Compact climb with views and wildflowers; official distance is “just under” 3 mi | [Sonoma County route feature](https://parks.sonomacounty.ca.gov/learn/blog/foothill-regional-parks-alta-vista-trail-gives-visitors-a-leg-up) |
| Riverfront Lake Trail | 2.18 mi · ~80 ft · 45–75 min · easy | Lakes/redwoods; S high / E low; low / low / moderate / moderate | Shaded warm-day fallback; county sources also round it to 2.3 mi | [Riverfront official page](https://parks.sonomacounty.ca.gov/visit/find-a-park/riverfront-regional-park) |
| North Sonoma Mountain Ridge | 7.6 mi · 1,140 ft · 4–5h30 · hard | Forest/creek/ridge; S moderate / E moderate; moderate / moderate / moderate / moderate | Solitude and mountain views; gain is from a secondary mapped route | [North Sonoma Mountain official page](https://parks.sonomacounty.ca.gov/visit/find-a-park/north-sonoma-mountain-regional-park-and-preserve) |
| Sonoma Ridge Trail | 9.5 mi · 1,500 ft · 4–5 hr · hard | Forest/redwoods/ridge; S high / E moderate; moderate / moderate / moderate / moderate | Long shaded historic-park objective; do not merge with the park's separate Sonoma Mountain Trail | [Jack London Park route page](https://jacklondonpark.com/bay-area-ridge-hiking-trail/) |
| Pioneer Nature Trail | 1.5 mi · ~40 ft · 45–75 min · easy | Old-growth redwood/creek; S high / E low; low / low / low / moderate | Accessible, photogenic, warm-weather-friendly; gain estimated | [Armstrong Redwoods official page](https://www.parks.ca.gov/?page_id=450) |
| East Ridge–Gilliam–Pool Ridge Loop | 5.6 mi · 1,100 ft · 3–4h15 · hard | Redwood/forest/ridge; S high / E moderate; low / low / moderate / high | Demanding shaded half-day; connector status must be checked | [California State Parks hike list](https://www.parks.ca.gov/?page_id=23369) |

### Sonoma Valley, Mayacamas, and Petaluma

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Sonoma Overlook with Upper Loop | 2.4 mi · ~400 ft · 1–1h30 · moderate | Grassland/oak/ridge; S low / E high; high / moderate / moderate / moderate | Town-combinable view hike; steward site is route-specific authority | [Sonoma Overlook Trail Stewards](https://overlookmontini.org/about/) |
| Bald Mountain Loop | 6.6 mi · 1,529 ft · 3–4 hr · hard | Mountain/ridge; S low / E high; high / high / moderate / high | Volcanic summit views; official guidance says 70–90% sun | [Sugarloaf hiking guide](https://sugarloafpark.org/activities/hiking/) |
| Pony Gate–Canyon Waterfall Loop | 2.0 mi · 450 ft · 1–1h30 · moderate | Creek/forest/canyon; S high / E low; low / low / moderate / high | Seasonal waterfall and 100+ steps; water is not guaranteed | [Sugarloaf official route map](https://sugarloafpark.org/wp-content/uploads/2023/12/Waterfall-hike-option-map-edited-Oct-2023-by-Alma-1.pdf) |
| Hood Mountain–Gunsight Rock | 7.1 mi · 2,454 ft · 4h30–6h30 · hard | Mountain/forest/ridge; S moderate / E moderate; high / moderate / moderate / high | Catalog's steepest local objective; gate, fire, and trail status critical | [Sonoma County peak guide](https://parks.sonomacounty.ca.gov/learn/blog/conquer-sonoma-countys-peaks-5-challenging-trails-with-stunning-views) |
| Ridge Trail–South Loop | 1.9 mi · ~300 ft · 50–80 min · moderate | Grassland/ridge; S low / E high; high / high / high / high | Short Petaluma views and sunset potential; gain estimated | [Helen Putnam official page](https://parks.sonomacounty.ca.gov/visit/find-a-park/helen-putnam-regional-park) |
| Bay View Vista | 7.6 mi · 750 ft · 3–4 hr · moderate | Grassland/wetland/ridge; S low / E high; high / high / high / high | Wildlife, quiet, and Bay views; cool dry days only | [Sonoma County peak guide](https://parks.sonomacounty.ca.gov/learn/blog/conquer-sonoma-countys-peaks-5-challenging-trails-with-stunning-views) |

### Sonoma Coast

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Bodega Head Loop | 1.89 mi · ~250 ft · 50–90 min · easy | Coastal bluff; S low / E high; low / high / moderate / high | Whale watching, photography, sunset; gain estimated | [2026 Sonoma Coast infosheet](https://www.parks.ca.gov/pages/451/files/SonomaCoastSP_Infosheet_8.5x11_062526_FINAL.pdf) |
| Kortum Trail, Wright's–Blind Beach | 5.0 mi · ~350 ft · 2–3 hr · moderate | Coastal bluff/beach; S low / E high; low / high / moderate / high | Signature bluff walk; official documents describe the 2.5-mi segment/endpoints inconsistently | [2026 Sonoma Coast infosheet](https://www.parks.ca.gov/pages/451/files/SonomaCoastSP_Infosheet_8.5x11_062526_FINAL.pdf) |
| Pomo Canyon from Shell Beach | 7.0 mi · ~1,300 ft · 4–5h30 · hard | Coast/redwood/canyon/ridge; S moderate / E moderate; moderate / moderate / high / high | Unusual coast-to-redwood objective; gain estimated | [Sonoma Coast park brochure](https://www.parks.ca.gov/pages/451/files/SonomaCoastSPFinalWebLayout2017.pdf) |
| Coastal Prairie Loop | 4.0 mi · ~600 ft · 1h45–2h45 · moderate | Coastal prairie/ridge; S low / E high; moderate / high / high / high | Quiet Jenner views; gain estimated | [Jenner Headlands official map](https://wildlandsconservancy.org/wp-content/uploads/2026/04/twc_jhp_trailmap_feb2024.pdf) |
| Salt Point Coastal Trail | 3.0 mi · ~100 ft · 1h15–2 hr · easy | Rocky coast/bluff; S low / E high; low / high / moderate / high | Geology, tidepools, and remote coast; exact sampler metrics are secondary | [Salt Point official page](https://www.parks.ca.gov/?page_id=453) |
| Pygmy Forest Loop | 3.8 mi · 646 ft · 1h45–2h30 · moderate | Pygmy forest/prairie; S moderate / E moderate; low / moderate / high / high | Rare botanical experience; sources describe 3.1- and 3.8-mi variants | [Salt Point official page](https://www.parks.ca.gov/?page_id=453) |
| Rhododendron–Chinese–Phillips Loop | 2.12 mi · 400 ft · 1–1h40 · moderate | Redwood/creek/botanical; S high / E low; low / low / high / high | Quiet spring rhododendrons; gain secondary and bloom timing variable | [Kruse reserve official page](https://www.parks.ca.gov/?page_id=448) |

### Marin and Mount Tamalpais

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Steep Ravine–Matt Davis Loop | 7.0 mi · 1,600 ft · 3h30–5 hr · hard | Redwood/creek/mountain/coast; S moderate / E moderate; low / moderate / high / high | Iconic stairs, water, and views; exact metrics are route-guide values | [Parks Conservancy Matt Davis page](https://www.parksconservancy.org/trails/matt-davis-trail) |
| Cataract–High Marsh–Kent–Benstein | 6.5 mi · ~1,200 ft · 3h30–5 hr · hard | Forest/creek/waterfall; S high / E low; low / low / high / high | Winter waterfall highlight; gain estimated | [One Tam route page](https://www.onetam.org/maps-trails/cataract-trail) |
| Ben Johnson–Dipsea Loop | 4.0 mi summer / 5.0 mi winter · 925 ft · 2h30–3h30 · hard | Old-growth redwood/forest; S high / E moderate; low / low / moderate / high | Muir Woods classic; reservations always required; seasonal bridge changes route | [NPS hiking page](https://www.nps.gov/muwo/planyourvisit/hike.htm) |
| Tennessee Valley to Beach | 3.5 mi · ~250 ft · 1h30–2h15 · easy | Coastal valley/beach; S low / E high; low / high / low / moderate | Popular relaxed coast option; seasonal flooding can block beach approach | [NPS route page](https://www.nps.gov/goga/planyourvisit/tennessee-valley-trail.htm) |

### Point Reyes

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Tomales Point Trail | 9.7 mi · ~1,200 ft · 4h30–6 hr · hard | Coastal ridge/grassland; S low / E high; moderate / high / moderate / high | Tule elk and long views; NPS also rounds to 9.5 mi, final 1.7 mi unmaintained | [NPS Tomales Point page](https://www.nps.gov/pore/planyourvisit/tomales_point.htm) |
| Chimney Rock Trail | 1.75 mi · ~200 ft · 50–90 min · easy | Coastal headland; S low / E high; low / high / moderate / high | Wildlife, flowers, whales, and photography; best paired with other Point Reyes stops | [NPS Chimney Rock page](https://www.nps.gov/pore/planyourvisit/chimney_rock.htm) |
| Abbotts Lagoon to Great Beach | 3.0 mi · ~150 ft · 1h30–2h30 · easy | Lagoon/wetland/beach; S low / E high; low / high / moderate / high | Strong birding and relaxed coast option; shorter turnarounds create mileage ambiguity | [NPS Abbotts Lagoon page](https://www.nps.gov/places/abbotts-lagoon.htm) |
| Alamere Falls via Wildcat Camp | 13.0 mi minimum · 1,500 ft · 6–8 hr · hard | Coast/forest/lakes/beach/waterfall; S moderate / E moderate; moderate / moderate / high / high | Full-day icon; never use unofficial cliff shortcut; tide/surf/daylight critical | [NPS Alamere Falls page](https://www.nps.gov/pore/planyourvisit/alamere_falls.htm) |

### Napa side

| Hike | Route facts | Environment and weather fit | Experience, season, and uncertainty | Source |
|---|---|---|---|---|
| Coyote Peak Loop | ~5.0 mi · ~1,000 ft · 2h30–3h45 · moderate | Redwood/forest/creek/ridge; S high / E moderate; moderate / low / moderate / high | Shaded Napa alternative; published 1,170-ft label may be summit elevation, not cumulative gain | [Bothe-Napa Valley official page](https://www.parks.ca.gov/?page_id=477) |
| Mount St. Helena Summit | 10.0 mi · 2,119 ft · 4h30–6h30 · hard | Mountain/forest/volcanic ridge; S low / E high; high / high / low / high | Big regional summit; official return distance is 10 mi, secondary trace is 10.7 mi | [Robert Louis Stevenson official page](https://www.parks.ca.gov/?page_id=472) |

## C. Curation rationale

### Why this works as a decision set

The inventory creates meaningful alternatives under the variables Event Radar already expects to combine:

- If the forecast is hot inland, the system can pivot from Taylor/Foothill/Tolay to Riverfront, Armstrong, Kruse, Muir Woods, or the coast.
- If coastal wind is excessive, it can pivot from Bodega/Kortum/Jenner/Point Reyes to protected forest and creek routes.
- If recent rain makes clay grasslands muddy, paved Spring Lake or lower-mud forest/coastal options remain.
- If recent rain has been moderate and conditions have stabilized, waterfall routes gain value without encoding “waterfall is flowing” as a permanent fact.
- Availability can compress from a full-day Alamere/Hood/Mount St. Helena choice to a one-hour Spring Lake, Colgan Creek, Crane Creek, Helen Putnam, or Bodega Head outing.
- Drive friction is part of the candidate identity. Chimney Rock is not a generic 1.75-mile walk; it is a destination option whose payoff improves when paired with wildlife, coast, and other Point Reyes stops.

### Redundancy removed

- Only one medium Annadel loop is retained; the official 7.4-mile Canyon–Spring Creek route is more distinctive than another central network combination.
- Taylor Mountain keeps two routes only because they occupy opposite product roles: a steep exposed workout and a short lower woodland/creek loop.
- Sugarloaf keeps a summit and a seasonal waterfall route; Vista Trail was redundant between them.
- Armstrong keeps a flat old-growth walk and a hard shaded loop; Jack London's Ancient Redwood route was cut because that niche was already strong.
- Mount Tam keeps three materially different experiences: Steep Ravine's coast-to-redwood loop, Cataract's waterfall watershed loop, and a reservation-controlled Muir Woods route.
- Point Reyes keeps four routes because each has a different decision role: wildlife endurance, short headland, relaxed wetland/beach, and full-day waterfall objective.

### Longer drives that justified inclusion

- **Salt Point coast and pygmy forest:** remote, geologically and botanically unusual, and meaningfully different from Bodega/Jenner.
- **Kruse Rhododendron:** short but seasonally distinctive shaded botany; can pair with Salt Point.
- **Mount Tam routes:** a higher-payoff redwood/waterfall/mountain category not fully replicated in Sonoma.
- **Point Reyes:** exceptional wildlife, headlands, wetlands, and the safe long route to Alamere.
- **Bothe and Mount St. Helena:** only two Napa-side entries, chosen for shaded-forest contrast and a major summit objective.

### Notable deliberate exclusions

- **Jenner Headlands Sea-to-Sky/Pole Mountain:** an older official map says 15 miles while the current official map says 18 miles round trip. Rather than normalize a major full-day route incorrectly, the catalog keeps the four-mile Coastal Prairie Loop and flags Sea-to-Sky for future route reconciliation.
- **Muir Woods Main Trail:** excellent, but its short old-growth niche is better served locally by Armstrong Pioneer; Ben Johnson–Dipsea makes the reservation/drive cost more worthwhile.
- **Sea Ranch Bluff Top:** beautiful but a long drive for a coastal-bluff experience already well covered closer to Santa Rosa.
- **Lake Sonoma routes:** omitted until an exact route has land-manager-grade metrics and trailhead identity strong enough for deterministic use.
- **Point Reyes Lighthouse walk:** worthwhile destination, but closer to an attraction/short walk than a catalog-defining hike.
- **Bear Valley/Arch Rock variants:** route endpoints and common naming are too easy to conflate; the selected Point Reyes routes already cover the major effort and environment roles.

## D. Data-quality audit

### Mechanical checks completed

- 35 records and 35 unique stable IDs.
- One identical field signature across all records.
- No missing official source URL, coordinate, numeric distance, numeric gain, numeric duration range, or controlled difficulty.
- All coordinates fall inside the expected North Bay/Marin/Point Reyes/Napa bounding area and refer to the stated route start rather than a park centroid.
- Every seasonal partition covers all 12 months without duplication or omission.
- Controlled values for difficulty, route type, three-level sensitivities, solo fit, scenic value, time of day, drive friction, coordinate precision, and confidence are consistent.
- No duplicate route names or obvious same-route reversals remain.

### Conflicting or route-dependent measurements

| Route | Conflict | Catalog treatment |
|---|---|---|
| Riverfront Lake Trail | County pages use 2.18 mi and rounded 2.3 mi | Retains 2.18; notes 2.3 rounding |
| Kortum Trail | Current infosheet lists 2.5 mi; older brochure wording implies different endpoints | Stores explicit Wright's–Blind five-mile return; confidence moderate |
| Salt Point Pygmy Forest | Friends route: 3.8 mi / ~2 hr; Gaia variant: 3.1 mi / 646 ft | Stores 3.8 mi and 646 ft but explicitly warns metrics describe different variants |
| Muir Woods Ben Johnson–Dipsea | NPS: 4 mi summer, 5 mi winter when seasonal bridge is removed | Stores 4 mi standard route and recurring 5 mi variant in notes |
| Tomales Point | NPS web page: 9.7 mi; NPS hiking guide: 9.5 mi | Retains 9.7 and records official rounding conflict |
| Abbotts Lagoon | Mileage differs by lagoon, bridge, or Great Beach turnaround | Endpoint is explicitly Great Beach; stores 3.0 mi return |
| Alamere Falls | NPS says 13 mi minimum | Stores 13.0 as minimum; route may be longer; shortcut prohibited |
| Bothe Coyote Peak | Napa guide's 1,170-ft label may be summit elevation, not cumulative gain | Stores a conservative 1,000-ft estimate and marks for GPX verification |
| Mount St. Helena | State Parks implies 10 mi return; secondary trace says 10.7 mi / 2,119 ft | Stores official 10.0 mi and secondary gain; notes conflict |

### Major inferred fields

The following are generally curation judgments, not agency quotations:

- shade and exposure;
- heat, wind, mud, and rain sensitivity;
- preferred/acceptable/poor months;
- best time of day;
- minimum reasonable daylight;
- solo fit;
- scenic value and experience tags;
- drive friction;
- estimated duration where an agency did not publish time;
- elevation gain where explicitly marked estimated.

The judgments derive from vegetation, route surface, grade, open-versus-forested terrain, official warnings, documented water features, coast/ridge setting, and route length. The JSON record-level `provenance` object names derived fields and states the basis; `data_quality.uncertainties` prevents inference from masquerading as direct fact.

### Coordinates

Most coordinates are mapped trailhead points with high confidence. Sugarloaf's Canyon parking area and Salt Point's Woodside/Pygmy start are marked `approximate_trailhead`. Before production import, the coding agent should run a map QA pass that renders all 35 points, checks road-side placement and entrance identity, and rejects park-centroid drift.

### Runtime checks that must remain outside this catalog

- official park and trail alerts, temporary closures, washouts, bridge/connector status, and prescribed-fire closures;
- wildfire smoke, fire-weather restrictions, and red-flag conditions;
- current weather and recent precipitation history;
- tides, surf, bluff hazards, and beach passability for Alamere and other coastal routes;
- wildlife closures and seasonal visitor-management rules at Point Reyes;
- Muir Woods parking/shuttle reservation availability and current entrance/transportation fees ([NPS reservation baseline](https://www.nps.gov/muwo/planyourvisit/know-before-you-go.htm));
- live parking availability, gates, hours, fee amounts, and road access;
- current trail condition reports and any stale closure documents still indexed online.

### Integration cautions

1. Do not use `preferred_months` as a hard gate. It is a stable prior that current forecast, daylight, recent rain, alerts, and user direction can override.
2. Do not score `rain_sensitivity: high` as always bad after rain. For waterfall routes, moderate prior rain plus stable trail conditions can be positive; active heavy rain is negative.
3. Do not interpret `solo_fit` as a safety guarantee. It describes whether solo participation is broadly normal/practical given route complexity and remoteness.
4. Preserve `route_start`, `route_end`, and `trail_sequence` when generating navigation or closure queries; park-level matching is not enough.
5. Revalidate moderate-confidence metrics when a canonical agency GPX or newer official map becomes available instead of silently overwriting them.

## Source hierarchy used

The research prioritizes California State Parks, Sonoma County Regional Parks, National Park Service, One Tam/Marin Water, The Wildlands Conservancy, and official park operating partners. Secondary route guides are used only where the official source establishes the park/route but does not publish exact gain or a standardized trace. Those cases are identified in the inventory and in JSON provenance.

