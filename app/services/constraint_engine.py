import re

from app.schemas.recommendation import ValidationResult
from app.schemas.recipe import Recipe
from app.schemas.user import NO_RESTRICTION_DIET_TYPES, UserProfile
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient


# --- Base allergen term sets --------------------------------------------
#
# These are the single source of truth for each allergen vocabulary. Public
# ALLERGEN_ALIASES keys below are *composed* from these (frozenset unions),
# never hand-copied -- so an edit to a base set is automatically reflected
# in every public key built from it, and two keys that are supposed to be
# identical (e.g. "dairy"/"milk") are literally the same object, not two
# hand-synced copies that can silently drift apart.
#
# This structure is a direct fix for a demonstrated hazard: commit 1cba9a9
# fixed a gap in "fish" (missing Worcestershire sauce) but missed the
# identical gap under "seafood", because nothing structurally tied the two
# hand-maintained sets together. See ALLERGEN_ALIASES's composition below
# and the structural invariant tests in test_constraint_engine.py.
#
# frozenset (not set) is deliberate: immutability means a later in-place
# edit (e.g. `ALLERGEN_ALIASES["fish"].add(...)`) can't mutate one base set
# and silently affect every other key composed from it.

_DAIRY = frozenset(
    {
        "butter",
        "casein",
        "cheddar",
        "cheese",
        "cream",
        "feta",
        "ghee",
        "grana padano",
        "Greek yogurt",
        "half and half",
        "half-and-half",
        "lactose",
        "mascarpone",
        "milk",
        "mozzarella",
        "paneer",
        # "panir": an accepted alternate transliteration of paneer (Indian
        # fresh cheese). Does not substring-match "paneer" in either
        # direction ("panir" and "paneer" share no common substring
        # relationship) -- two staged candidate recipes ("Pudina Paneer"
        # imp_53717b715fb95252, "Roomali Paneer" imp_f53043dfe62a5136) use
        # this spelling ("panir"/"grated panir") and were confirmed to leak
        # past a milk allergy before this addition. Verified 2026-07-25: no
        # unrelated ingredient name in the active corpus, staged candidate
        # batches, or scraped source contains "panir" as a substring, so
        # this addition carries no lookalike-collision risk requiring a
        # _LOOKALIKE_EXCLUSIONS carve-out (unlike "brie"/"capon"/"tripe").
        "panir",
        "parmesan",
        # "parmigiano", "pecorino", "grana padano", and "romano" are hard
        # cheeses (all definitionally milk products) that were missing from
        # this set even though "parmesan" (the same cheese, different name)
        # was already present -- a bare "parmigiano" corpus row was
        # servable to milk-allergic users before this addition. "romano" has
        # a same-word lookalike ("romano bean(s)", a legume with no dairy
        # content at all) handled per-term via _LOOKALIKE_EXCLUSIONS below,
        # the same mechanism that already guards "chestnut"/"water chestnut".
        "parmigiano",
        "pecorino",
        "ricotta",
        "romano",
        "whey",
        "yogurt",
        # "yoghurt": the British spelling. The extra "h" defeats a substring
        # match against the existing "yogurt" entry ("yoghurt" does not
        # contain "yogurt" as a substring, nor the reverse) -- a bare
        # "natural yoghurt" corpus row was servable to milk-allergic users
        # before this addition, added 2026-07-19 per the diet-leak audit
        # exposed by the A1 scraped-archive re-import (task A1 revise
        # round; docs/BACKLOG.md).
        "yoghurt",
        # "curd": coagulated milk, by definition -- cheese curds, "curds and
        # whey" (the nursery-rhyme name for the same dairy product). A bare
        # "lemon curd" corpus row standardly contains butter/eggs/sugar and
        # no other _DAIRY term catches it (added 2026-07-19, A1 revise
        # round). NOTE the lookalike exclusion below: "bean curd" is tofu
        # (soy, not dairy) and is explicitly carved out via
        # _LOOKALIKE_EXCLUSIONS["curd"] so this addition doesn't
        # over-block soy-based bean-curd rows.
        "curd",
        # --- 2026-07-20, systematic ground-truth-vs-production vocabulary
        # diff closure (docs/BACKLOG.md) -- 9 dairy terms confirmed present
        # in scripts/audit_diet_leaks.py's independent GROUND_TRUTH_DAIRY
        # ground truth but missing from this production table. Corpus-hit
        # counts below are measured against the current 3,859-recipe active
        # corpus (2026-07-20; supersede the 2026-07-19 diff's now-stale
        # counts, which were taken before A3's re-grounding run and B5 --
        # corpus composition has since shifted slightly). All 9 are
        # unambiguously dairy for THIS allergen/dairy-free purpose;
        # "gruyere"'s SEPARATE, still-open question (is PDO-governed gruyere
        # vegetarian, i.e. rennet source for the _RENNET_SET_CHEESES
        # vegetarian check) is out of scope here -- gruyere contains milk
        # regardless of rennet source, so this addition is correct
        # independent of that unresolved question (see "Gorgonzola / gruyere
        # PDO-verification cluster" in docs/BACKLOG.md).
        #   - "gruyere": a Swiss/French cow's-milk cheese by definition. 8 hits.
        "gruyere",
        #   - "provolone": an Italian cow's-milk cheese by definition. 5 hits.
        "provolone",
        #   - "creme fraiche": cultured dairy cream by definition. 4 hits.
        "creme fraiche",
        #   - "custard": egg-and-MILK (or cream) based dessert/sauce by
        #     definition; "custard powder" (the corpus's dominant spelling)
        #     is prepared with milk, not a milk-free product on its own.
        #     5 hits.
        "custard",
        #   - "brie": a French cow's-milk soft cheese by definition. 3 raw
        #     substring hits, but see _LOOKALIKE_EXCLUSIONS["brie"] below for
        #     a genuine false-positive this addition would otherwise
        #     introduce ("O'Brien potatoes" contains the literal substring
        #     "brie") -- 2 real corpus hits once that carve-out is applied.
        "brie",
        #   - "kefir": a fermented MILK drink by definition. 2 hits.
        "kefir",
        #   - "camembert": a French cow's-milk soft cheese by definition.
        #     1 hit.
        "camembert",
        #   - "queso": Spanish for "cheese" -- "queso fresco"/"queso"
        #     generically refers to a dairy cheese in every standard
        #     culinary sense. 1 hit.
        "queso",
        #   - "gouda": a Dutch cow's-milk cheese by definition. 0 corpus
        #     hits today -- future-import defense only.
        "gouda",
        # "cool whip", "whipped topping", "dream whip": whipped-topping/dessert-mix
        # products whose ingredient statements standardly include sodium caseinate
        # (a milk-protein derivative) regardless of "non-dairy" labeling -- FARE's
        # milk-allergy hidden-sources guidance names whipped toppings and non-dairy
        # creamers explicitly; this is the product class, not the literal word
        # "non-dairy", so it is pinned by product name rather than by the labeling
        # phrase (a bare "dairy" substring rule was considered and rejected -- it
        # would wrongly flag the genuinely dairy-free "soy dairy firm tofu" row on
        # imp_c028d6ed99ee5945 "Tofu"). Verified 2026-07-25 against the active
        # corpus: 42 recipes carry one of these three terms; 6
        # (imp_0d423c1a38025015 "Root Beer Cake", imp_16f4e589c05656e2 "Lemonade
        # Cake #3", imp_54324a408dcb5e89 "Sour Cherry Jell-O Pie",
        # imp_5aa78000db5c5464 "Taffy Apple Salad 11", imp_916a677794bb5087
        # "Holiday Poke Cake", imp_97fda67ff1d45e65 "Spaghetti Fruit Salad") were
        # genuinely unprotected for a milk allergy before this addition; the
        # remaining 36 already failed via a co-occurring dairy ingredient, so
        # measured over-block delta is 0. No collision risk: "Miracle Whip"
        # (mayonnaise, no dairy) does not contain any of these three phrases as a
        # substring, verified against the corpus.
        "cool whip",
        "whipped topping",
        "dream whip",
    }
)

# Satay/saté sauce is a peanut-based sauce (ground peanuts, oil, and
# aromatics) in its standard Southeast Asian preparations -- by
# definition, not a sourced claim. Peanut is a major allergen designated
# by FALCPA (21 U.S.C. Sec. 321(qq)) and by EU Regulation 1169/2011,
# Annex II, point 5 ("Peanuts") -- those two statute/regulation cites are
# verified. "sate"/"saté" are accepted alternate transliterations of the
# same dish/sauce.
# "enchilada sauce" (added 2026-07-19, adjudication_20260719T083748Z.md
# hidden_017 TRUE_VIOLATION): FARE (Food Allergy Research & Education)'s
# peanut page lists "Enchilada sauce" verbatim under "Other Possible
# Sources of Peanut" (some commercial/restaurant formulations use peanut
# butter or ground peanuts as a thickener/flavor enhancer). Same
# compound-term precedent as "satay sauce" above -- pinned as the full
# phrase, not a bare "sauce"/"enchilada" head noun, because every corpus
# occurrence already contains the full phrase and a bare head noun would
# needlessly widen the substring-matching surface (the corpus has zero
# bare "sauce"/"enchilada" rows today, verified, so this addition cannot
# reverse-match an unrelated ingredient). Measured over-block (2026-07-19,
# advisor-ratified, active-corpus scope): 3 recipes (imp_4599012eed065be5
# "Mexican-Style Meatballs in Red Sauce", imp_c304eff4b40c579d "Linda's
# Enchiladas", imp_ed2c12ce84705381 "Mexicali Casserole"). A 4th matching
# row lives on imp_4632c3cbea4957e4 "Turkey Enchiladas", which is already
# quarantined for an unrelated reason and therefore doesn't count in the
# active-corpus over-block figure.
_PEANUT = frozenset(
    {
        "enchilada sauce",
        "groundnut",
        "peanut",
        "peanut butter",
        "peanut oil",
        "peanuts",
        "sate",
        "satay",
        "satay sauce",
        "saté",
    }
)

_TREE_NUT = frozenset(
    {
        "almond",
        "almonds",
        # Amaretti (Italian almond macaroons), marzipan, frangipane, praline,
        # nougat, and gianduja are almond- and/or hazelnut-based confections
        # or pastes by definition (not merely "may contain" products), so
        # they are sourceable additions rather than a general/unsourced
        # audit expansion.
        "amaretti",
        # Amaretto (the liqueur): the dominant commercial brand (Disaronno)
        # is apricot-kernel-based and marketed as nut-free, but some other
        # amaretto brands/recipes are almond-based, and AAAAI guidance notes
        # post-distillation nut infusions/flavorings can still trigger
        # reactions; FARE's "foods and ingredients to avoid" guidance for
        # tree-nut allergy includes nut extracts and nut-flavored
        # distillates generally. Given that ambiguity, this project's policy
        # (see the nougat/Worcestershire over-blocking notes below) resolves
        # toward blocking rather than excluding by base rate. Note: because
        # matching is substring-based, "amaretti" above does NOT also match
        # "amaretto" -- it is listed here as its own explicit entry.
        "amaretto",
        # Brazil nut is a tree nut explicitly named alongside almond,
        # hazelnut, walnut, cashew, pecan, pistachio, and macadamia in EU
        # Regulation 1169/2011, Annex II, point 8 ("Nuts"), and in FDA's
        # FALCPA tree-nut guidance.
        "brazil nut",
        "brazil nuts",
        "cashew",
        # Frangipane is, by definition, an almond-cream pastry filling
        # (ground almonds, butter, sugar, egg) -- not a source-verified
        # claim; FARE's published tree-nut hidden-sources list does not
        # currently name frangipane explicitly.
        "frangipane",
        # Gianduja is, by definition, a hazelnut-and-chocolate paste (the
        # base of Nutella-style spreads) -- FARE's tree-nut hidden-sources
        # guidance lists it explicitly.
        "gianduja",
        "hazelnut",
        "macadamia",
        # Marzipan is almond paste (ground almonds + sugar) by definition;
        # FARE's tree-nut hidden-sources guidance names marzipan as a common
        # concealed tree-nut source.
        "marzipan",
        # Traditional nougat (e.g. nougat de Montelimar, and the nougat in
        # many chocolate bars) contains almonds and/or hazelnuts by
        # definition. FARE's PEANUT page (not the tree-nut page) lists
        # "Nougat and marzipan" as possible peanut sources; the tree-nut
        # classification here rests on the definitional almond/hazelnut
        # content, not on that peanut-page citation. This over-blocks the
        # rarer nut-free nougat -- an accepted tradeoff for an
        # anaphylaxis-class allergen (see the Worcestershire/fish note below
        # for the same reasoning applied to fish).
        "nougat",
        "pecan",
        # Pine nut is retained as a tree nut in FDA's January 2025 Edition 5
        # "Questions and Answers Regarding Food Allergens" guidance, which
        # narrowed the previously ~23-item tree-nut list to 12 named tree
        # nuts and kept "Pine nut (Pinon nut)" among them.
        "pine nut",
        "pine nuts",
        "pistachio",
        # Chestnut (genus Castanea) is a regulated tree nut per FARE's
        # Tree Nut allergy page, which names "Chestnut" alongside almond,
        # walnut, cashew, etc. in its avoid-list. NOTE: the bare noun
        # "chestnut" also substring-matches "water chestnut" (Eleocharis
        # dulcis), an unrelated aquatic sedge/corm that is NOT a tree nut --
        # see _LOOKALIKE_EXCLUSIONS below, which suppresses that specific
        # false positive without weakening this entry for a real chestnut.
        "chestnut",
        "chestnuts",
        # Praline paste (French/Belgian confectionery) is traditionally
        # almond- and/or hazelnut-based; American-style pralines are
        # pecan-based. Either way it is tree-nut derived -- FARE's tree-nut
        # hidden-sources guidance lists praline.
        "praline",
        "walnut",
    }
)

_WHEAT = frozenset(
    {
        "biscuit",
        "bread",
        "bulgur",
        "couscous",
        "cracker",
        "crouton",
        "farro",
        "fettuccine",
        "filo",
        "flour",
        "graham cracker",
        # Standard brewed/commercial soy sauce is fermented with wheat, and
        # wheat is routinely declared on US soy-sauce labels (FALCPA);
        # tamari and explicitly-labeled gluten-free soy sauce are the
        # wheat-free exception, not the rule -- and a bare corpus row (just
        # "soy sauce") cannot prove it's the labeled-GF kind. Same reasoning
        # class as the Worcestershire/fish over-blocking note above: ambiguity
        # resolves toward blocking for an anaphylaxis-adjacent, celiac-serious
        # allergen. Commercial hoisin sauce standardly contains wheat flour
        # (Lee Kum Kee's declared hoisin sauce ingredients list wheat flour;
        # celiac-organization gluten-free shopping guidance lists hoisin sauce
        # as a food that typically contains gluten). Commercial teriyaki sauce
        # is soy-sauce-based and commonly declares wheat (e.g. Kikkoman
        # Teriyaki Sauce's ingredient label lists wheat). All three are pinned
        # as their full two-word/three-word phrase, per the "sea bass"
        # precedent above -- not the bare "hoisin"/"teriyaki" head noun --
        # because every corpus occurrence already contains the full phrase
        # and a bare head noun would needlessly widen the substring-matching
        # surface. Known, deliberate side effect: SYNONYMS in
        # app/utils/ingredient_normalizer.py maps "tamari" -> "soy sauce", so
        # adding "soy sauce" here also makes a bare "tamari" ingredient row
        # fail closed for wheat/gluten allergies/diet (7 corpus rows as of
        # this change). That is intentional, not an accident: non-GF-labeled
        # tamari can still contain wheat, and a bare corpus row cannot prove
        # otherwise -- the exact same "can't prove the safe variant" logic as
        # the soy-sauce entry itself.
        "hoisin sauce",
        "lasagna",
        "linguine",
        "macaroni",
        "pasta",
        "pastry",
        "phyllo",
        "semolina",
        # "spaghetti" also substring-matches "spaghetti squash" (a vegetable,
        # gluten-free in reality) -- accepted as an over-cautious false
        # positive rather than a missed detection, consistent with existing
        # "cornflour"/"eggplant" substring trade-offs elsewhere in this file.
        "spaghetti",
        "seitan",
        "soy sauce",
        "teriyaki sauce",
        "tortilla",
        "wheat",
        "whole wheat pasta",
        # "pretzel": a wheat-flour baked good by definition. Same bare-row
        # logic as the existing soy-sauce entry above -- a labeled
        # gluten-free pretzel is the specialty exception, not something a
        # bare corpus row can prove, so ambiguity resolves toward blocking.
        # Added 2026-07-19 (A1 revise round, diet-leak audit).
        "pretzel",
        # "pita": wheat flatbread. Lookalike carve-out: "pitaya" (dragon
        # fruit, gluten-free) is unrelated and explicitly excluded via
        # _LOOKALIKE_EXCLUSIONS["pita"] below -- same water-chestnut-class
        # mechanism as "chestnut"/"romano". Added 2026-07-19.
        "pita",
        # "orzo": a durum-wheat pasta shaped like a large grain of rice --
        # same logic as "pretzel" above (no bare-row way to prove a
        # gluten-free variant). Added 2026-07-19.
        "orzo",
    }
)

# "bean curd" (added 2026-07-19, A1 revise round): coagulated soymilk --
# tofu's other common English name. Soy is a FALCPA major allergen (21
# U.S.C. Sec. 321(qq)); a corpus row like "cube bean curd" contains neither
# "soy" nor "tofu" as a substring, so it leaked past a soy allergy before
# this addition (found via the A1 diet-leak audit re-run). See
# _LOOKALIKE_EXCLUSIONS["curd"] for the corresponding dairy-side carve-out
# (bean curd must never trip the *dairy* "curd" term).
_SOY = frozenset(
    {"bean curd", "edamame", "miso", "soy", "soy sauce", "soya", "tamari", "tempeh", "tofu"}
)

_EGG = frozenset({"egg", "egg whites", "eggs", "mayonnaise"})

# Crustaceans (crab, lobster, shrimp, ...) and mollusks (clam, mussel,
# oyster, scallop) are the two biological groupings that make up
# "shellfish". The bare term "shellfish" itself is deliberately filed under
# _MOLLUSK (not _CRUSTACEAN): it's an ambiguous umbrella term that could
# refer to either group, and "crustacean" below explicitly re-adds it (see
# that composition) so a crustacean-only allergy still catches an
# ambiguous "shellfish stock" ingredient rather than risk missing it.
_CRUSTACEAN = frozenset(
    {
        "crab",
        "crayfish",
        # "Crawfish" is the common US-regional spelling of the same
        # crustacean as "crayfish" (Cambaridae/Astacidae) -- not a separate
        # species, just an alternate spelling that "crayfish" does not
        # substring-match.
        "crawfish",
        "lobster",
        "prawn",
        "shrimp",
    }
)
# "calamari"/"octopus"/"squid" are cephalopod mollusks (class Cephalopoda,
# phylum Mollusca), not crustaceans -- biologically the same broad grouping
# as clam/mussel/oyster/scallop above, which this codebase already treats as
# _MOLLUSK beyond the narrower FALCPA/EU Annex II "molluscs" species lists,
# fail-closed and consistent with those existing entries. Added 2026-07-20
# (systematic ground-truth-vs-production vocabulary diff closure,
# docs/BACKLOG.md): squid 3 corpus hits, calamari/octopus 0 (future-import
# defense), measured against the current 3,859-recipe active corpus. Also
# added to MEAT_ALIASES below for the independent vegetarian/vegan
# diet-type check -- same dual-membership pattern as "gelatin"/
# "worcestershire"/"caviar".
_MOLLUSK = frozenset({"calamari", "clam", "mussel", "octopus", "oyster", "scallop", "shellfish", "squid"})

_FISH = frozenset(
    {
        "anchovy",
        # "catfish"/"swordfish": fish species. Found 2026-07-20 (this task,
        # "derive_allergen_labels natural-language robustness" Part B --
        # corpus-wide sweep of common fish species against _FISH's then
        # current contents, prompted by an advisor review's bass/sea-bass
        # finding -- see this task's report for the factual correction that
        # "sea bass" was already present in _FISH at the commit the review
        # cited). 4 corpus hits each (current 3,884-recipe active corpus,
        # 2026-07-20; catfish: "catfish fillets"/"catfish fillets (4 oz.
        # each)"; swordfish: "swordfish fillets"/"fresh swordfish steaks"/
        # "swordfish steaks or 6 salmon steaks"/"swordfish steaks... or 4
        # tuna steaks..."). Measured delta: 0 on both -- every one of these 8
        # occurrences was ALREADY correctly detected before this addition,
        # because "catfish"/"swordfish" both literally CONTAIN the bare
        # "fish" substring already in this set ("cat"+"fish",
        # "sword"+"fish"), so the pre-existing bare "fish" term already
        # substring-matches them. This addition is pure vocabulary
        # completeness/label-accuracy (so `derive_allergen_labels`'s output
        # names the specific species rather than relying on a coincidental
        # substring match), not a new detection -- reported honestly as 0
        # delta rather than overclaiming a safety fix, matching this
        # project's "measure, don't assume" discipline. No collision risk:
        # neither is a substring of any other corpus ingredient name.
        "catfish",
        "swordfish",
        "cod",
        "fish",
        "flounder",
        # "grouper": a fish species. Found 2026-07-20 (this task, same sweep
        # as catfish/swordfish above). 1 corpus hit (current 3,884-recipe
        # active corpus): imp_096552b6325d5645 "Sopa Leao Velloso", ingredient
        # "grouper (4 lbs)". Measured delta: a GENUINE 1-recipe under-block
        # fix, not redundant -- that recipe's only other seafood ingredients
        # are shrimp/mussels/clams/crabmeat/lobster (crustacean/mollusk), so
        # it was already correctly blocked for "shellfish"/"crustacean"/
        # "seafood" allergies but NOT for a "fish"-only allergy (a materially
        # different, narrower allergen category) before this addition -- this
        # is exactly the missed-real-fish-content class of gap the advisor
        # review's (factually incorrect, re: sea bass specifically) finding
        # was pointing at, confirmed real here instead. No collision risk:
        # "grouper" is not a substring of any other corpus ingredient name.
        "grouper",
        # "mackerel": a fish species. Found 2026-07-20 (same sweep). 2 corpus
        # hits (current 3,884-recipe active corpus): imp_388d3cea0e235e0b
        # "Fish En Escabeche" ("...or 1 lb mackerel fillet...", alongside
        # "haddock fillets", already caught) and imp_d3b6dcc2b0af528b
        # "Brittany Mixed Fish Soup" ("Flounder, mackerel, cod, or haddock",
        # alongside "fish"/"flounder"/"cod"/"haddock", already caught).
        # Measured delta: 0 -- both occurrences are redundant with an
        # already-matching _FISH term in the same ingredient row/recipe, pure
        # vocabulary completeness. No collision risk found.
        "mackerel",
        # "perch": a fish species. Found 2026-07-20 (same sweep). 0 corpus
        # hits today (checked against the active corpus, the quarantine
        # sidecar, and the seed set) -- future-import defense only, same
        # basis as this task's other 0-hit MEAT_ALIASES/_FISH additions (see
        # "venison"/"quail"/"pheasant" etc. below). No collision risk found
        # (0 hits means nothing to collide with today).
        "perch",
        # "tilapia": a fish species. Found 2026-07-20 (same sweep). 1 corpus
        # hit (current 3,884-recipe active corpus): imp_4e2b084f47675396
        # "Fish Fillets", ingredient "fish fillet (any kind-I used Tilapia)".
        # Measured delta: 0 -- the same ingredient row already contains the
        # bare word "fish" directly, so this was already correctly detected;
        # pure vocabulary completeness. No collision risk found.
        "tilapia",
        # Gelatin and isinglass: a documented fail-closed POLICY CHOICE, not a
        # claim that gelatin is usually fish -- mainstream US retail gelatin
        # (e.g. Knox, Jell-O) is porcine/bovine, and FALCPA requires the
        # specific fish species to be declared on labels when gelatin IS
        # fish-derived. But fish gelatin is a real, non-hypothetical
        # commercial class: kosher gelatin is frequently fish-derived (fish
        # is pareve, so it's the common kosher substitute for the
        # non-kosher-by-default bovine/porcine kind), FARE (Food Allergy
        # Research & Education) lists gelatin as a hidden source of fish, and
        # isinglass (fish-bladder collagen, used historically in gelatin and
        # in fining beer/wine) is fish by definition. A bare "unflavored
        # gelatin" corpus row cannot rule out the fish-derived kind. This is
        # an anaphylaxis-class allergen, so ambiguity resolves toward
        # blocking (same reasoning class as the Worcestershire/amaretto/
        # nougat notes elsewhere in this file). Over-block cost is measured,
        # not assumed: 61/4052 recipes (1.5%) become unservable to fish/
        # seafood-allergic users specifically as a result of this entry.
        # "gelatin" already lives in MEAT_ALIASES above for the unrelated
        # vegetarian/vegan diet-type check (standard gelatin is animal-
        # derived, full stop, regardless of species) -- this is an additive,
        # independent membership in this allergen table, mirroring the
        # worcestershire dual-membership pattern documented at that entry
        # and at MEAT_ALIASES's "worcestershire" line. Deliberately NOT added
        # to _CRUSTACEAN or _MOLLUSK: gelatin/isinglass are never shellfish-
        # derived, so adding them there would be an unjustified over-block
        # with no sourcing behind it, unlike the fish case above.
        "gelatin",
        "haddock",
        "halibut",
        "isinglass",
        "salmon",
        "sardine",
        # "sea bass" is pinned as the full two-word term, not bare "bass":
        # bare "bass" would widen the substring-matching surface (e.g.
        # instruments, other unrelated words) for no corpus benefit, since
        # every corpus occurrence ("filets of fresh sea bass", "sea bass
        # fillet") already contains the substring "sea bass".
        "sea bass",
        "snapper",
        "sole",
        "trout",
        "tuna",
        "white fish",
        # "caviar" is fish roe (sturgeon or other fish species) by definition
        # -- FALCPA's fish allergen designation and EU Regulation 1169/2011,
        # Annex II, point 4 ("Fish") both cover roe/caviar as fish-derived.
        # Added 2026-07-20 (systematic ground-truth-vs-production vocabulary
        # diff closure, docs/BACKLOG.md): 0 corpus hits today (future-import
        # defense only, verified against the current 3,859-recipe active
        # corpus). Also added to MEAT_ALIASES below -- same dual-membership
        # pattern as "gelatin"/"worcestershire" (independent allergen-table
        # and vegetarian/vegan diet-type memberships, mirroring that these
        # two checks share vocabulary but are not the same check).
        "caviar",
        # Traditional Worcestershire sauce is fermented with anchovies, a
        # fish allergen under FALCPA and under EU Regulation 1169/2011,
        # Annex II, point 4 ("Fish"); FARE (Food Allergy Research &
        # Education)'s fish page lists Worcestershire sauce as a common
        # hidden source of fish. Anchovy-free "vegan" Worcestershire-style
        # sauces do exist, so this over-blocks them -- an accepted tradeoff
        # for an anaphylaxis-class allergen, where a false positive costs
        # one recipe and a false negative can be fatal. "worcestershire"
        # already appears in MEAT_ALIASES below for the unrelated
        # vegetarian/vegan diet-type check; this is an additive, independent
        # entry in the allergen table and does not change that path.
        "worcestershire",
        "worcestershire sauce",
    }
)

ALLERGEN_ALIASES = {
    "dairy": _DAIRY,
    "milk": _DAIRY,
    "peanut": _PEANUT,
    "peanuts": _PEANUT,
    "tree nut": _TREE_NUT,
    # "nuts" is the union of the tree-nut and peanut vocabularies -- composed
    # here, not hand-copied, so it can never silently drift from either
    # source set (see those sets' inline comments for the citation behind
    # each addition; no new citations are introduced by this union).
    "nuts": _TREE_NUT | _PEANUT,
    # "nut" (singular): same union, same object, as "nuts" -- mirrors the
    # existing "peanut"/"peanuts" and "dairy"/"milk" duplicate-key pattern
    # above. Added 2026-07-20 (direction-aware lookalike matching, revise
    # round 1) so a bare singular "nut" allergy string actually reaches the
    # nut vocabulary via _expand_allergen_terms: normalize_ingredient("nut")
    # does not depluralize an already-singular word, so without this key a
    # "nut" allergy had no route into _TREE_NUT | _PEANUT at all (unlike
    # "nuts", which normalizes/matches straight to this same key). See the
    # _BARE_NUT_TRIGGER_VOCABULARY comment near contains_allergen for the
    # under-block regression this closes. INDEX_ALLERGENS
    # (recipe_indexing_service.py) enumerates its own fixed 8-key list for
    # Chroma metadata and does not iterate ALLERGEN_ALIASES keys, so this
    # addition changes no indexed metadata field.
    "nut": _TREE_NUT | _PEANUT,
    "wheat": _WHEAT,
    # "malt" (barley-derived) and "rye" are gluten but not wheat -- added
    # only at this composition, not in _WHEAT. Same for "krispies"/"cereal"
    # below (added 2026-07-19, adjudication_20260719T083748Z.md diet_023
    # TRUE_VIOLATION cure): these are barley-MALT vehicles, not wheat, so
    # they belong here and NOT in _WHEAT -- contains_allergen(..., ["wheat"])
    # must stay False for a bare "Rice Krispies" row.
    #   - "krispies": Kellogg's Rice Krispies contain barley malt
    #     flavoring; Kellogg's own allergen statement does not list them as
    #     gluten-free. Direction-safe both ways (neither "krispies" nor any
    #     corpus ingredient name is a substring of the other in an unsafe
    #     way -- verified against the corpus). 8 corpus rows (measured
    #     2026-07-19: imp_13f9f264a2c6580d, imp_17037d8dc09459ea,
    #     imp_172df04faf2a5c66, imp_25b9fc8ec0fb58cb, imp_3b30b27e5edf5d3f,
    #     imp_4b6bf6dc2acb55d5, imp_4e58b5fba51c5fcc, imp_cc173d9e8fc451c9
    #     -- the last is the adjudicated diet_023 case, "Fresh Cherry
    #     Tart").
    #   - "cereal": closes the in-corpus brand-cereal class direction-safely
    #     -- same "can't prove the labeled-GF/non-malted variant from a
    #     bare row" logic as the existing soy-sauce entry in _WHEAT above.
    #     Real corpus rows this closes: "Post Grape-Nuts cereal" (wheat +
    #     malted barley flour, Post's own ingredient list), "corn flakes
    #     cereal" / "crispy rice cereal" / "puffed corn cereal" (Kellogg's
    #     malt flavoring, same as Rice Krispies), "Cheerios toasted oat
    #     cereal" (General Mills' US Cheerios ARE independently
    #     gluten-free-labeled -- this is a KNOWN, ACCEPTED over-block for
    #     that specific brand: Health Canada does not accept General
    #     Mills' gluten-free process validation for the Canadian market,
    #     and Cheerios formulations sold outside the US/Canada are not
    #     uniformly GF-labeled either, so a bare, unqualified "cereal" row
    #     still cannot affirmatively prove the specific GF-labeled US
    #     product -- the same fail-closed logic as the soy-sauce entry,
    #     applied consistently even though this one case is a real,
    #     measured, known false positive). Measured over-block: 28 corpus
    #     rows total (2026-07-19), gluten-constrained users only -- see
    #     docs/BACKLOG.md for the full row-by-row list.
    #   - "corn flakes", "post toasties", "rice krispies", "grape-nuts":
    #     precise compound brand-cereal terms, added 2026-07-19 (direction-
    #     aware lookalike matching fix, docs/BACKLOG.md). Previously these
    #     could NOT be added: bidirectional substring matching's reverse arm
    #     would have matched bare "rice"/"grape"/"corn" ingredient rows
    #     corpus-wide (e.g. a bare "corn" ingredient reverse-matching "corn
    #     flakes" and wrongly failing gluten-free for a plain vegetable).
    #     `_recipe_contains_any_term`/`_any_term_matches` is now one-directional
    #     (a term may only match as a substring OF a longer ingredient name,
    #     never the reverse), so these compound terms are safe to add: a bare
    #     "corn"/"rice"/"grape" ingredient can never reverse-match into them.
    #     These close the exact gap the "krispies"/"cereal" broader terms
    #     above could not: a brand-cereal row naming neither "cereal" nor
    #     "krispies" (e.g. a bare "corn flakes" ingredient with no "cereal"
    #     suffix, or "Post Toasties" -- Post's own toasted-corn-flakes brand,
    #     same barley-malt-flavoring hazard class as Rice Krispies). See the
    #     6-recipe manual-quarantine release this fix enables, this same
    #     round (docs/BACKLOG.md "Manual quarantine: brand-cereal rows..."
    #     entry). The existing "krispies"/"cereal" broader terms are KEPT,
    #     not replaced -- they still catch brand names/phrasings that don't
    #     literally contain these four compound terms.
    "gluten": _WHEAT
    | {
        "barley",
        "malt",
        "rye",
        "krispies",
        "cereal",
        "corn flakes",
        "post toasties",
        "rice krispies",
        "grape-nuts",
    },
    "soy": _SOY,
    "soya": _SOY,
    "egg": _EGG,
    "eggs": _EGG,
    # "shellfish" = every crustacean + every mollusk (including the bare
    # "shellfish" term itself, filed under _MOLLUSK -- see that set's
    # comment).
    "shellfish": _CRUSTACEAN | _MOLLUSK,
    # "crustacean" explicitly adds the ambiguous bare term "shellfish": a
    # crustacean allergy must still catch an ingredient like "shellfish
    # stock", which may well contain crustaceans, rather than risk a false
    # negative on ambiguous wording (allergen ambiguity resolves toward
    # blocking throughout this table -- see the nougat/amaretto notes above).
    "crustacean": _CRUSTACEAN | {"shellfish"},
    "fish": _FISH,
    # "seafood" is the union of fish + crustaceans + mollusks -- composed
    # here so it can never silently miss a term present in any of those
    # three sets (that composition is what makes it a structural superset,
    # verified by the invariant tests in test_constraint_engine.py, rather
    # than a hand-copied list of the other three).
    "seafood": _FISH | _CRUSTACEAN | _MOLLUSK,
    "sesame": frozenset({"sesame", "sesame oil", "sesame seeds", "tahini"}),
}

# Meat/poultry (and their processed/derived forms) aren't in ALLERGEN_ALIASES
# because they aren't allergens, but they're what makes a recipe non-vegetarian.
# Fish/shellfish/seafood are deliberately NOT duplicated here -- vegetarian and
# vegan reuse ALLERGEN_ALIASES's fish/shellfish/seafood/crustacean sets below
# so there is exactly one, already-tested substring-matching definition of
# "does this recipe contain fish" for both allergy and diet-type checks to
# share, instead of two lists that can silently drift apart (that drift, for
# dairy/gluten, was root-cause of the 2026-07 corpus diet-leak audit).
#
# Sourced from the 2026-07 corpus diet-leak audit (43.7% vegan / 9.4%
# vegetarian leak rate against the 4,238-recipe Food.com import). Extend this
# set, not a separate list, if a future audit finds another gap. No need for
# compound entries like "chicken broth"/"beef stock": _recipe_contains_any_term
# substring-matches the bare "chicken"/"beef" against those directly.
MEAT_ALIASES = {
    "bacon",
    "beef",
    # "bologna": a USDA-standardized cured meat sausage (9 CFR 319.140).
    # Verified no collision with "bolognese" -- "bologna" is NOT a
    # substring of "bolognese" (b-o-l-o-g-n-E vs b-o-l-o-g-n-A, differ at
    # the 7th letter), so this addition cannot false-flag a meat sauce name
    # via substring match. Added 2026-07-19 (A1 revise round, diet-leak
    # audit -- "Hobo Buns" carried a bare "bologna" row with no meat
    # ingredient the vegetarian scan previously recognized).
    "bologna",
    # "bratwurst": a German pork/veal sausage by definition. The existing
    # bare "sausage" entry below does NOT catch it -- "sausage" is not a
    # substring of "bratwursts" (the corpus's plural spelling). Added
    # 2026-07-19 (A1 revise round, diet-leak audit).
    "bratwurst",
    # "brisket": a beef primal cut. Added 2026-07-20 (systematic
    # ground-truth-vs-production vocabulary diff closure, docs/BACKLOG.md):
    # confirmed against scripts/audit_diet_leaks.py's independent
    # GROUND_TRUTH_MEAT_POULTRY_FISH ground truth. 8 corpus hits (current
    # 3,859-recipe active corpus, 2026-07-20), all "beef brisket"/"corned
    # beef brisket" phrasings that already independently substring-match the
    # pre-existing bare "beef" term -- measured over-block delta versus the
    # pre-change vegetarian-passing baseline: 0 (see this task's report).
    "brisket",
    # "calamari": the common culinary name for squid (a cephalopod mollusk,
    # not a crustacean). Also added to ALLERGEN_ALIASES["fish"]'s sibling
    # _MOLLUSK set below (see that set's inline comment for the taxonomy
    # citation) -- dual membership mirrors "gelatin"/"worcestershire"/
    # "caviar". 0 corpus hits today -- future-import defense only.
    "calamari",
    # "capon": a castrated rooster, raised specifically for meat -- poultry,
    # by definition. 0 corpus hits today (future-import defense), but see
    # _LOOKALIKE_EXCLUSIONS["capon"] below: "capon" is a literal substring of
    # "caponata" (a vegetarian eggplant dish), so a bare addition here
    # without that carve-out would wrongly exclude vegetarian caponata rows
    # once "capon" does appear in a future import.
    "capon",
    # "caviar": fish roe by definition. Also added to ALLERGEN_ALIASES["fish"]
    # above (see that entry's inline comment) -- dual membership mirrors
    # "gelatin"/"worcestershire". 0 corpus hits today -- future-import
    # defense only.
    "caviar",
    "chicken",
    "chorizo",
    "duck",
    # "gelatin" now also lives in ALLERGEN_ALIASES["fish"] (see that set's
    # inline comment for the fish-gelatin/isinglass sourcing and the accepted
    # over-block cost). This entry here is the pre-existing, independent
    # vegetarian/vegan diet-type check and is unaffected by that addition --
    # mirroring the "worcestershire" dual-membership pattern (that term is
    # independently a member of both this set and ALLERGEN_ALIASES["fish"]
    # above; see that set's inline comment).
    "gelatin",
    "goose",
    # "grouper": a fish species. The generic bare "fish" term in
    # ALLERGEN_ALIASES["fish"] only substring-matches ingredient names
    # literally containing the word "fish" -- a species-name-only row like
    # "grouper (4 lbs)" needs its own explicit entry. Added 2026-07-20
    # (systematic ground-truth-vs-production vocabulary diff closure,
    # docs/BACKLOG.md). 1 corpus hit; measured over-block delta: 0.
    "grouper",
    "ham",
    "hot dog",
    "lamb",
    "lard",
    # "mackerel": a fish species, same "generic 'fish' term doesn't catch a
    # bare species name" reasoning as "grouper" above. Added 2026-07-20.
    # 2 corpus hits; measured over-block delta: 0.
    "mackerel",
    # Standard marshmallows are set with gelatin (animal-derived; see the
    # "gelatin" entry above), per the Vegetarian Resource Group's Vegetarian
    # FAQ, which names gelatin as a common hidden non-vegetarian ingredient.
    # Filed in MEAT_ALIASES (not a separate vegan-only list) so vegetarian
    # inherits the block too -- marshmallow-set desserts are a genuine
    # vegetarian violation, not just a vegan one -- via the existing
    # MEAT_ALIASES -> _VEGETARIAN_EXCLUDED_TERMS -> _VEGAN_EXCLUDED_TERMS
    # composition below, rather than a hand-copied duplicate entry that
    # could drift. Corpus variants ("marshmallow creme"/"cream", "mini"/
    # "miniature marshmallows") all substring-match the bare "marshmallow".
    "marshmallow",
    # "meatball": a ground-meat preparation by definition (the corpus's only
    # occurrence, "small meatballs" in Meatball Soup, contains no other
    # already-covered meat term). Added 2026-07-20 (systematic
    # ground-truth-vs-production vocabulary diff closure, docs/BACKLOG.md).
    # 1 corpus hit; measured over-block delta: 0.
    "meatball",
    # "octopus": a cephalopod mollusk, same taxonomy note as "calamari"
    # above -- also added to the sibling _MOLLUSK set below. 0 corpus hits
    # today -- future-import defense only.
    "octopus",
    "pancetta",
    "pepperoni",
    # "perch": a fish species, same "generic 'fish' term doesn't catch a
    # bare species name" reasoning as "grouper"/"mackerel" above. Added
    # 2026-07-20. 0 corpus hits today -- future-import defense only.
    "perch",
    # "pheasant": game-bird poultry by definition. Added 2026-07-20. 0
    # corpus hits today -- future-import defense only.
    "pheasant",
    "pork",
    "prosciutto",
    # "quail": game-bird poultry by definition. Added 2026-07-20. 0 corpus
    # hits today -- future-import defense only.
    "quail",
    "rabbit",
    # "salami": a cured meat sausage by definition. Added 2026-07-20
    # (systematic ground-truth-vs-production vocabulary diff closure,
    # docs/BACKLOG.md). 3 corpus hits; measured over-block delta: 0 (every
    # corpus salami row already independently fails vegetarian via another
    # already-covered meat term in the same recipe).
    "salami",
    "sausage",
    # "sirloin": a beef primal cut. The reverse-arm substring match this
    # enables (a longer recipe term like "sirloin tip roast" containing the
    # shorter "sirloin") is meat either way, so it's fail-closed correct,
    # not an over-block risk. Added 2026-07-19 (A1 revise round, diet-leak
    # audit -- this term was previously masked for one corpus recipe by an
    # unrelated "pepper"/"pepperoni" substring collision; see
    # docs/BACKLOG.md for that separate, NOT-fixed-here finding).
    "sirloin",
    # "squid": a cephalopod mollusk, same taxonomy note as "calamari"/
    # "octopus" above -- also added to the sibling _MOLLUSK set below. Added
    # 2026-07-20 (systematic ground-truth-vs-production vocabulary diff
    # closure, docs/BACKLOG.md). 3 corpus hits; measured over-block delta: 0
    # (every corpus squid row already independently fails vegetarian via
    # another already-covered fish/seafood term in the same recipe --
    # ALLERGEN_ALIASES["fish"]/["shellfish"] already flow into
    # _VEGETARIAN_EXCLUDED_TERMS, so this addition is defense-in-depth for a
    # hypothetical future squid-only recipe, not a change in current
    # coverage).
    "squid",
    "steak",
    "suet",
    # "tilapia": a fish species, same "generic 'fish' term doesn't catch a
    # bare species name" reasoning as "grouper"/"mackerel"/"perch" above.
    # Added 2026-07-20. 1 corpus hit; measured over-block delta: 0.
    "tilapia",
    # "tripe": an offal meat (stomach lining) by definition. 0 corpus hits
    # today (future-import defense), but see _LOOKALIKE_EXCLUSIONS["tripe"]
    # below: "tripe" is a literal substring of "striped" -- t-r-i-p-e appears
    # contiguously inside s-t-r-i-p-e-d (verified character-by-character). A
    # bare addition here without that carve-out would make any future
    # "striped bass"/"striped anything" ingredient row wrongly register as
    # containing tripe, an unrelated, incorrect substring match with no real
    # tripe content -- the same class of false positive as
    # "chestnut"/"water chestnut" or "capon"/"caponata". Added 2026-07-20
    # (systematic ground-truth-vs-production vocabulary diff closure,
    # docs/BACKLOG.md).
    "tripe",
    "turkey",
    "veal",
    # "venison": deer meat by definition. Added 2026-07-20. 0 corpus hits
    # today -- future-import defense only.
    "venison",
    "worcestershire",
}
HONEY_ALIASES = {"honey"}

# Cheeses whose name is governed by a Protected Designation of Origin (PDO/
# AOP) standard that mandates animal rennet -- so a *compliant* product sold
# under that name cannot be vegetarian, regardless of any individual
# producer's marketing claims. This is a narrower, name-level rule than "all
# hard cheeses are non-vegetarian" (many hard cheeses use microbial/
# fermentation-produced chymosin and are genuinely vegetarian):
#   - Parmigiano-Reggiano PDO: calf rennet mandated by the consortium
#     production standard.
#   - Pecorino Romano PDO: lamb rennet mandated by the consortium production
#     standard.
#   - Grana Padano PDO: calf rennet mandated by the consortium production
#     standard.
# Deliberately REJECTED, not just omitted:
#   - "gorgonzola", "gruyere": their governing specs were not verified for
#     this change -- backlogged (docs/BACKLOG.md), not silently assumed.
#   - "manchego": Manchego PDO explicitly permits non-animal (e.g. microbial)
#     coagulants, so a compliant vegetarian Manchego genuinely exists -- this
#     is not the same rule shape as parmigiano/pecorino/grana padano above.
# Generic "cheese"/"cheddar"/"mozzarella" deliberately stay vegetarian-OK:
# mainstream vegetarian-rennet versions of those are the norm, not the
# exception. Compound "X cheese" term shapes (e.g. "parmesan cheese") are
# deliberately NOT added here: _recipe_contains_any_term's substring matching
# is bidirectional (`term in recipe_term or recipe_term in term`), so a term
# like "parmesan cheese" would reverse-match every bare "cheese" ingredient
# in the corpus (37 bare "cheese" rows) as if it were specifically a
# rennet-set PDO cheese -- a catastrophic over-block. Only bare cheese-name
# terms are used, exactly like the existing "parmesan"/"cheddar" entries in
# _DAIRY above.
#
# NOT added to MEAT_ALIASES: MEAT_ALIASES feeds a planned title-integrity
# extension (app/services/corpus_import/title_ingredient_integrity.py) where
# cheese words would be semantically wrong (cheese is not meat) and would
# mis-quarantine unrelated recipes.
_RENNET_SET_CHEESES = frozenset({"parmesan", "parmigiano", "pecorino", "grana padano", "romano"})

_VEGETARIAN_EXCLUDED_TERMS = (
    MEAT_ALIASES
    | ALLERGEN_ALIASES["fish"]
    | ALLERGEN_ALIASES["shellfish"]
    | ALLERGEN_ALIASES["seafood"]
    | ALLERGEN_ALIASES["crustacean"]
    | _RENNET_SET_CHEESES
)
# Vegan = vegetarian's exclusions plus the animal products vegetarians still
# eat (dairy, eggs, honey). Dairy/egg terms come from the same ALLERGEN_ALIASES
# sets contains_allergen uses -- this is also why "butter", "parmesan", "sour
# cream", "mayonnaise", and "heavy cream" (all audit-surfaced vegan leaks) need
# no separate entry here: they already substring-match "cream"/"cheese"/"egg"
# etc. via the shared alias sets.
_VEGAN_EXCLUDED_TERMS = _VEGETARIAN_EXCLUDED_TERMS | ALLERGEN_ALIASES["dairy"] | ALLERGEN_ALIASES["egg"] | HONEY_ALIASES

DIET_TYPE_EXCLUDED_TERMS = {
    "vegetarian": _VEGETARIAN_EXCLUDED_TERMS,
    "vegan": _VEGAN_EXCLUDED_TERMS,
}


# --- Lookalike exclusions ---------------------------------------------------
#
# _recipe_contains_any_term matches by substring, which is normally the
# right call for safety (see the Worcestershire/nougat over-blocking notes
# above -- ambiguity should resolve toward blocking). But some ingredient
# names are a different kind of case: a term that is a *literal* substring
# of an unrelated food, with no real uncertainty about safety at all.
#
# "chestnut" is the motivating example: "water chestnut" (Eleocharis dulcis)
# is an aquatic sedge/corm, botanically and culinarily unrelated to tree
# nuts (genus Castanea) -- it never contains tree nut, so blocking it isn't
# an extra-cautious tradeoff, it's simply wrong, and wrong warnings train
# allergic users to stop trusting the tool. This table exists to carve out
# exactly that kind of case, without weakening the underlying term.
#
# CRITICAL SAFETY SEMANTICS: this exclusion is evaluated per (term,
# recipe_term) PAIR inside the matching loop below, never at the
# whole-recipe level. If a recipe has two separate ingredients -- one real
# ("fresh chestnuts") and one lookalike ("water chestnuts") -- the real
# ingredient's own term is a different `recipe_term` value and is NOT
# suppressed; only the lookalike ingredient's own match is. A per-recipe
# exclusion would let a real allergen hide behind an unrelated lookalike
# ingredient in the same recipe -- see the "hiding" regression test in
# test_constraint_engine.py.
_LOOKALIKE_EXCLUSIONS: dict[str, frozenset[str]] = {
    "chestnut": frozenset({"water chestnut", "water chestnuts"}),
    "chestnuts": frozenset({"water chestnut", "water chestnuts"}),
    # "romano" is now a dairy/rennet-set-cheese term (see _DAIRY and
    # _RENNET_SET_CHEESES above), but "romano bean(s)" is an unrelated
    # legume (Phaseolus vulgaris, the flat Italian green/dry bean) that never
    # contains cheese or rennet -- same lookalike shape as water chestnut,
    # wired identically.
    "romano": frozenset({"romano bean", "romano beans"}),
    # "pita" (added to _WHEAT 2026-07-19, A1 revise round) vs "pitaya":
    # dragon fruit (Hylocereus/Selenicereus spp.), a cactus fruit, is
    # genuinely gluten-free and botanically unrelated to wheat flatbread --
    # same water-chestnut-class false positive. Corpus grep (2026-07-19,
    # 4,232-recipe post-migration corpus): 0 "pitaya" rows -- pure
    # future-import defense today, not a measured fix.
    "pita": frozenset({"pitaya"}),
    # "curd" (added to _DAIRY 2026-07-19, A1 revise round) vs "bean curd":
    # bean curd is tofu (coagulated SOYMILK), never dairy -- water-chestnut
    # class. CRITICAL: this is evaluated per (term, recipe_term) pair (see
    # this table's module-level docstring above), so a recipe carrying BOTH
    # "bean curd" and a real dairy curd ingredient (e.g. "cheese curds")
    # still correctly flags dairy -- only the "bean curd" ingredient's own
    # match is suppressed, never the whole recipe. See the "hiding
    # regression" test in test_constraint_engine.py and the audit-side
    # correction in scripts/audit_diet_leaks.py (GROUND_TRUTH_FALSE_
    # POSITIVE_PAIRS), which must never disagree with this entry.
    "curd": frozenset({"bean curd", "bean curds"}),
    # "capon" (added to MEAT_ALIASES 2026-07-20, systematic
    # ground-truth-vs-production vocabulary diff closure, docs/BACKLOG.md) is
    # a literal substring of "caponata", a vegetarian eggplant dish (no
    # capon/poultry content) -- water-chestnut class. 0 "caponata" corpus
    # rows as of this change (future-import defense, not a measured fix
    # today), but confirmed as a live landmine that would have wrongly
    # excluded any future caponata recipe from vegetarian/vegan results.
    # Mirrored into scripts/audit_diet_leaks.py's
    # GROUND_TRUTH_FALSE_POSITIVE_PAIRS, which must never disagree with this
    # entry.
    "capon": frozenset({"caponata"}),
    # "tripe" (added to MEAT_ALIASES 2026-07-20, same task) is a literal
    # substring of "striped" -- t-r-i-p-e appears contiguously inside
    # s-t-r-i-p-e-d (verified character-by-character) -- so "striped bass"/
    # any "striped X" ingredient name would otherwise wrongly register as
    # containing tripe. 0 "striped" corpus rows as of this change
    # (future-import defense, added preemptively alongside "tripe" itself so
    # the landmine never goes live even for a day). Mirrored into
    # scripts/audit_diet_leaks.py's GROUND_TRUTH_FALSE_POSITIVE_PAIRS.
    "tripe": frozenset({"striped", "striped bass"}),
    # "brie" (added to _DAIRY 2026-07-20, same task) is a literal substring
    # of "o'brien" -- b-r-i-e appears contiguously inside o-'-b-r-i-e-n
    # (verified character-by-character) -- so "O'Brien potatoes" (a diced
    # hash-brown-style potato product, no dairy content), a REAL, currently
    # present corpus ingredient (imp_d1c5441716f4524f, "30 Minute Smoked
    # Sausage and Corn Chowder"), would otherwise wrongly register as
    # containing brie. Discovered during this change's own over-block
    # measurement (not part of the original task-spec diff, which only
    # flagged capon/caponata and tripe/striped) -- same water-chestnut-class
    # false positive, fixed on the same basis. "obrien" (no apostrophe) is
    # included defensively too: ingredient names in this corpus are raw
    # free text with no guaranteed consistent apostrophe/quote-mark usage,
    # and an apostrophe-free "obrien" spelling would defeat the
    # apostrophe'd "o'brien" carve-out above without also matching this
    # entry. Mirrored into scripts/audit_diet_leaks.py's
    # GROUND_TRUTH_FALSE_POSITIVE_PAIRS.
    "brie": frozenset({"o'brien", "obrien"}),
}


def _is_lookalike_match(term: str, recipe_term: str) -> bool:
    """True if the match between `term` and `recipe_term` is fully explained
    by a known lookalike phrase for `term` (see _LOOKALIKE_EXCLUSIONS), and
    should therefore NOT count as a real allergen/diet hit.

    Implementation: remove every occurrence of each known lookalike phrase
    from `recipe_term`, then re-check whether `term` still appears in what's
    left. If it doesn't, the original match existed only because of the
    lookalike phrase, so it's suppressed. If `term` still appears (e.g. a
    contrived ingredient name containing the real word *and* the lookalike
    phrase), the match stands -- this function only ever narrows a match
    down to nothing, never widens it.
    """
    lookalikes = _LOOKALIKE_EXCLUSIONS.get(term)
    if not lookalikes:
        return False
    stripped = recipe_term
    for lookalike in lookalikes:
        stripped = stripped.replace(lookalike, "")
    return term not in stripped


def _normalized_terms(values: list[str] | set[str] | frozenset[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        normalized = normalize_ingredient(value)
        if normalized:
            terms.add(normalized.lower())
        if value:
            terms.add(value.lower().strip())
    return {term for term in terms if term}


def _expand_allergen_terms(allergies: list[str]) -> set[str]:
    terms = _normalized_terms(allergies)
    expanded = set(terms)
    for allergy in terms:
        expanded.update(_normalized_terms(ALLERGEN_ALIASES.get(allergy, set())))
    return expanded


def _recipe_safety_terms(recipe: Recipe) -> set[str]:
    # Safety is name-based and quantity-independent: an allergen present in any
    # amount is a violation, so only ingredient names (never amount/unit) feed
    # allergen matching.
    return _normalized_terms([*(item.name for item in recipe.ingredients), *recipe.allergens])


def derive_allergen_labels(ingredient_names: list[str]) -> list[str]:
    """Deterministically derive which ALLERGEN_ALIASES keys a set of ingredient
    names implies, using the same membership table AND the same matching
    mechanism as contains_allergen. This is the reverse direction: given
    ingredients, produce labels (used for imported/candidate recipes'
    `allergens` field and for Chroma index metadata) rather than given an
    allergy, test membership. Never trust a source-provided allergen field
    for imports — derive it here instead.

    SUBSTRING-CONSISTENT WITH contains_allergen (docs/BACKLOG.md,
    "`derive_allergen_labels` natural-language robustness"): a prior version
    of this function did EXACT-SET membership matching (tuned for the old
    atomized CSV's single-word ingredient names), so it silently under-
    covered natural-language ingredient text with descriptor clauses or "X or
    Y" alternatives (e.g. "2 eggs, slightly beaten") that contains_allergen's
    own substring matching already handles correctly. This version reuses
    `_expand_allergen_terms` and `_any_term_matches` — the exact same two
    primitives `contains_allergen` calls — per candidate ALLERGEN_ALIASES
    key, plus the same bare-nut-word compensation `contains_allergen` applies
    (see `_BARE_NUT_WORD`/`_BARE_NUT_TRIGGER_VOCABULARY` below — required so
    a bare, unqualified "nuts" ingredient row derives "tree nut"/"peanut"/
    "nuts" here exactly as it is blocked there; that compensation is NOT
    reachable via ordinary substring matching alone, only via the
    word-boundary check). This makes the CLOSED-LOOP INVARIANT hold by
    construction: for every ingredient list and every allergen key L, `L in
    derive_allergen_labels(names)` iff `contains_allergen(recipe_with_these_
    ingredient_names, [L])` is True — see the corpus-wide property test in
    test_constraint_engine.py. Zero changes to contains_allergen itself: this
    function only ever calls the same already-tested primitives, never
    modifies them.

    Deliberately returns every matching ALLERGEN_ALIASES key as-is (e.g. both
    "dairy" and "milk" if either fires — their alias sets are identical, so
    they always co-match) rather than collapsing synonyms to one canonical
    label per class. Collapsing would require an opinionated synonym->label
    mapping (e.g. is a "seafood" match reported as "fish"?) that isn't implied
    by the existing table and would change which labels appear without any
    test coverage backing that choice — a needless risk in an allergen-safety
    path. Callers needing metadata-flag membership (recipe_indexing_service)
    only ever check the 8 canonical keys directly, so this is a drop-in,
    superset-only replacement for the prior exact-set logic (see acceptance
    criterion 1 in the backlog entry above: new labels are always a superset
    of what the exact-set version derived, verified corpus-wide).
    """
    terms = _normalized_terms(ingredient_names)
    has_bare_nut_word = _ingredient_names_have_bare_nut_word(ingredient_names)
    labels: set[str] = set()
    for allergen_key in ALLERGEN_ALIASES:
        expanded_terms = _expand_allergen_terms([allergen_key])
        matched = _any_term_matches(terms, expanded_terms)
        if not matched and expanded_terms & _BARE_NUT_TRIGGER_VOCABULARY and has_bare_nut_word:
            matched = True
        if matched:
            labels.add(allergen_key)
    return sorted(labels)


def _any_term_matches(candidate_terms: set[str], terms: set[str]) -> bool:
    """One-directional substring match: True iff some `term` appears WITHIN
    some `candidate_terms` entry (`term in candidate`), and that match is not
    fully explained by a known lookalike phrase (see `_is_lookalike_match`).

    Direction is deliberate and safety-load-bearing (docs/BACKLOG.md,
    "direction-aware lookalike matching mechanism"): a compound allergen/diet
    term may match as a substring of a longer ingredient name (e.g. "peanut
    butter" matching within "creamy peanut butter"), but a bare ingredient
    word must never match merely because it happens to be a substring of a
    longer, unrelated compound term (e.g. bare "pepper" must never match
    "pepperoni", and bare "soy" must never match "soy sauce" -- see
    `_recipe_contains_any_term`'s prior bidirectional implementation, which
    had exactly that reverse-direction hazard). `term in candidate` alone
    already subsumes the exact-equality case (a string is always `in`
    itself), so there is no separate `==` check.
    """
    for term in terms:
        for candidate in candidate_terms:
            if term in candidate and not _is_lookalike_match(term, candidate):
                return True
    return False


def _recipe_contains_any_term(recipe: Recipe, terms: set[str]) -> bool:
    # Deliberately NOT ingredient_matches(term, recipe_term) here: that function
    # re-runs normalize_ingredient on `term` internally, which re-applies
    # SYNONYMS on top of the normalization _normalized_terms already did when
    # building `terms`. For a broad category word like "chicken", SYNONYMS
    # maps it to a specific cut ("chicken breast"), which then fails to
    # substring-match every OTHER cut ("chicken drumstick", "chicken broth",
    # "chicken bouillon", ...) -- silently defeating "chicken" as an exclusion
    # term for anything but literal chicken breast. `terms` and `recipe_terms`
    # are both already fully normalized (via _normalized_terms, which keeps
    # both the raw and normalized form of each value), so a direct substring
    # test is sufficient and doesn't re-trigger that collision.
    recipe_terms = _recipe_safety_terms(recipe)
    return _any_term_matches(recipe_terms, terms)


# --- Bare "nut"/"nuts" ingredient (direction-aware lookalike matching fix,
# 2026-07-19, docs/BACKLOG.md) -----------------------------------------------
#
# A bare, unqualified "nuts" ingredient row is a real, measured shape in this
# corpus (16 active-corpus recipes, e.g. imp_2cb3642cd927507e "Applesauce
# Cake", imp_38d021312e6751c9 "Deep Dark Secret", imp_6ab74a6c238451a3
# "Banana-Nut Muffins" -- verified 2026-07-19). Before this fix,
# `_recipe_contains_any_term`'s bidirectional substring matching's REVERSE
# arm accidentally caught these rows (bare "nut" is a substring of every
# compound tree-nut term: "walnut", "hazelnut", "brazil nut", "pine nut",
# ...). Removing the reverse arm would silently lose that detection unless
# compensated for.
#
# The obvious fix -- adding bare "nut"/"nuts" as ordinary ALLERGEN_ALIASES
# substring terms -- was tried and is UNSAFE: forward substring matching
# would then match "nut"/"nuts" against every OTHER word that merely
# *contains* those letters, which is a large, real false-positive surface
# with zero nut content: "butternut squash" (a vegetable), "water chestnut"
# (the EXISTING, explicitly-tested lookalike carve-out --
# test_water_chestnut_not_over_blocked_by_tree_nut_additions caught this
# regression directly), "chestnut" (unrelated to the bare-noun question --
# already its own explicit term), "nutmeg" (a spice, unrelated botanically),
# and "coconut" (disputed/labeling-nuanced, not something this addition
# should silently decide). This is the same "durum"/"rum" false-positive
# class this project explicitly avoids elsewhere (see
# GROUND_TRUTH_GLUTEN's docstring in scripts/audit_diet_leaks.py) -- not
# ambiguity that should resolve toward blocking, but a plain, objectively
# wrong match with no real nut-vocabulary payoff.
#
# Instead, "nut"/"nuts" is matched only as a whole, standalone WORD (regex
# word boundaries), never as a substring of a longer word. This still
# catches every real corpus shape ("nuts", "nuts, Chopped", "chopped nuts",
# "-1 cup nuts, chopped", "nuts (walnuts or pecans are good)") while never
# matching "butternut squash"/"water chestnut"/"chestnut"/"nutmeg"/
# "coconut". Net safety effect measured as zero over-block delta versus the
# pre-fix baseline: every one of the 16 corpus rows this catches was ALREADY
# being blocked before this fix, via the reverse-arm bug this fix removes --
# so this is a same-behavior-preserving migration onto a precise, direction-
# safe mechanism, not a new block, and it does not reintroduce the
# over-broad match a plain substring term would have.
#
# An ambiguous "nuts" row could equally be peanuts (not just tree nuts), so
# this check applies to BOTH the tree-nut and peanut allergy keys (and the
# "nuts" key, their union) -- mirroring how the pre-existing bare
# "shellfish" term is a member of both _MOLLUSK and, via composition, the
# "crustacean" key.
_BARE_NUT_WORD = re.compile(r"\bnuts?\b", re.IGNORECASE)

# UNDER-BLOCK REGRESSION FIX (2026-07-20, direction-aware lookalike matching,
# revise round 1): the trigger for the bare-nut-word check above must fire on
# a *semantic* condition, not a hardcoded list of literal allergy-string
# spellings. The prior version matched `{allergy.lower().strip() for allergy
# in allergies}` (the RAW, unnormalized allergy strings) against a hardcoded
# frozenset of exact spellings ({"tree nut", "nuts", "peanut", "peanuts"}).
# UserProfile.allergies is genuine free text (app/schemas/user.py) with no
# upstream canonicalization, so that raw-string check silently missed every
# spelling variant _expand_allergen_terms already knows how to normalize:
# plural "tree nuts", case variants ("Tree Nuts"), and the bare singular
# "nut" -- confirmed as a real regression by advisor review reproducing
# directly against the pre-fix baseline (4a97b80~1). Bare "nuts"/"nut"/
# "tree nut"/"peanut"/"peanuts" ingredient rows must be caught for BOTH
# singular and plural, any-case allergy spellings -- see
# derivative_022/023/025/026/028 and hidden_023..028 in the benchmark case
# set, which document that expectation.
#
# Fixed by reusing _expand_allergen_terms (the SAME normalization every other
# allergen check in this module already goes through -- no second
# normalization path) and checking membership in the nut ingredient
# vocabulary instead of literal allergy spellings. "nut" (singular) is now
# its own ALLERGEN_ALIASES key (see that dict) precisely so
# _expand_allergen_terms(["nut"]) reaches this vocabulary the same way
# _expand_allergen_terms(["nuts"]) already did.
_BARE_NUT_TRIGGER_VOCABULARY = _normalized_terms(_TREE_NUT | _PEANUT)


def _recipe_has_bare_nut_word(recipe: Recipe) -> bool:
    return any(_BARE_NUT_WORD.search(item.name) for item in recipe.ingredients)


def _ingredient_names_have_bare_nut_word(ingredient_names: list[str]) -> bool:
    """Same word-boundary bare-"nut"/"nuts" check as `_recipe_has_bare_nut_word`
    directly above, applied to raw ingredient-name strings instead of
    `Recipe.ingredients` items -- `derive_allergen_labels` takes raw names,
    not a `Recipe`, and it needs this exact check (not a re-derivation) to
    stay substring-consistent with `contains_allergen`'s own bare-nut
    compensation OR-arm (see `contains_allergen` below): a bare, unqualified
    "nuts" ingredient row (16 real corpus recipes, e.g. "Applesauce Cake") is
    caught by `contains_allergen(recipe, ["tree nut"])`/(["peanut"]) ONLY via
    that second OR-arm, never via ordinary substring matching -- so without
    this helper, `derive_allergen_labels` would silently miss the "tree
    nut"/"nuts"/"peanut" labels for those recipes even though
    `contains_allergen` correctly blocks them, breaking both the `new_labels
    ⊇ old_labels` superset guarantee and the closed-loop invariant.
    """
    return any(_BARE_NUT_WORD.search(name) for name in ingredient_names if name)


def contains_allergen(recipe: Recipe, allergies: list[str]) -> bool:
    expanded_terms = _expand_allergen_terms(allergies)
    if _recipe_contains_any_term(recipe, expanded_terms):
        return True
    if expanded_terms & _BARE_NUT_TRIGGER_VOCABULARY and _recipe_has_bare_nut_word(recipe):
        return True
    return False


def contains_disliked_ingredient(recipe: Recipe, disliked_ingredients: list[str]) -> bool:
    for disliked in disliked_ingredients:
        if any(ingredient_matches(disliked, item.name) for item in recipe.ingredients):
            return True
    return False


def violates_diet_type(recipe: Recipe, diet_type: str | None) -> bool:
    if not diet_type or diet_type.lower() in NO_RESTRICTION_DIET_TYPES:
        return False

    requested = diet_type.lower()
    # recipe.diet_tags is deliberately NEVER read here. A prior version
    # returned False whenever `requested` was among the recipe's own
    # diet_tags, bypassing every exclusion-vocabulary scan below for tagged
    # recipes. Adjudication proved this admits genuinely unsafe recipes:
    # diet_014 (adjudication_20260718T090522Z.md) served r_004, a
    # hand-authored seed tagged "vegetarian" that carries a bare `parmesan`
    # row (traditional parmesan is rennet-set, not vegetarian under the
    # fail-closed convention) -- the tag opt-out let it through without an
    # ingredient scan. A self-asserted tag can neither ADMIT (loosen the
    # scan) nor REJECT (this function only ever returns True from a scan
    # match, so a tag was never able to reject on its own) a diet outcome;
    # only the deterministic scans below decide.
    if requested == "gluten-free":
        # Same substring-matching path as contains_allergen, not recipe.allergens
        # (which derive_allergen_labels populates via exact-set membership and
        # misses compound names like "buttermilk" or "gravy" -- see audit).
        return contains_allergen(recipe, ["gluten"])
    if requested == "dairy-free":
        return contains_allergen(recipe, ["dairy"])
    if requested in DIET_TYPE_EXCLUDED_TERMS:
        return _recipe_contains_any_term(recipe, _normalized_terms(DIET_TYPE_EXCLUDED_TERMS[requested]))

    # UserProfile.diet_type is validated against SUPPORTED_DIET_TYPES at
    # intake (app.schemas.user), so an unrecognized value here means a caller
    # (e.g. RecipeDiscoveryRequest, which has its own freeform diet_type) is
    # asking about a diet_type this function was never taught to enforce.
    # Returning False would silently claim the recipe is safe for that diet;
    # fail loudly instead.
    raise ValueError(f"violates_diet_type does not enforce diet_type {diet_type!r}")


def violates_cook_time(recipe: Recipe, max_cook_time: int | None) -> bool:
    return bool(max_cook_time and recipe.cook_time_min and recipe.cook_time_min > max_cook_time)


def validate_recipe(recipe: Recipe, user_profile: UserProfile) -> ValidationResult:
    if contains_allergen(recipe, user_profile.allergies):
        return ValidationResult(is_valid=False, rejection_reason="Contains a user allergen")
    if contains_disliked_ingredient(recipe, user_profile.disliked_ingredients):
        return ValidationResult(is_valid=False, rejection_reason="Contains a disliked ingredient")
    if violates_diet_type(recipe, user_profile.diet_type):
        return ValidationResult(is_valid=False, rejection_reason=f"Violates diet type: {user_profile.diet_type}")
    if violates_cook_time(recipe, user_profile.max_cook_time_min):
        return ValidationResult(is_valid=False, rejection_reason="Exceeds maximum cooking time")
    return ValidationResult(is_valid=True)
