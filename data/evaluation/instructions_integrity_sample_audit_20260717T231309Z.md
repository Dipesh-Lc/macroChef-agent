# Sample-audit adjudication — instructions-integrity run 20260717T231309Z (round 1)

- Sample: n=40, seed 20260718, stratified per spec §3, drawn from the
  1130-row flagged set (report 20260717T231309Z). Adjudicator:
  orchestrator session, 2026-07-18. Advisor review: round-2 ruling.
- Verdicts: CORRECT_QUARANTINE (CQ) or FALSE_POSITIVE (FP), per-case
  citable reason. Acceptance bar: ≤2/40 FP.
- **RESULT: 31 CQ / 9 FP → BREACH (9 > 2). Miss spot-check (n=15, seed
  20260718): 2 miss classes found → BREACH (bar: 0).** Both breaches
  invoke the pre-registered on-breach path: cited fixes, full re-run,
  fresh sample seed incremented. This is revision round 2 of the
  spec's maximum two.

## Per-case verdicts (Tier A/B sample)

1. imp_e7fb53c18ced5dc0 Beer Batter, crustacean — **FP**. "Dip fresh
   shrimp, mushrooms or veggies": intended-use with listed alternatives;
   the batter's own rows are complete and shrimp-free (Fish Marinade
   class — the dish is the batter, the dippable is user-supplied).
2. imp_9b2c1d45a9f55ef1 Alfredo Sauce, crustacean — **FP**. "(If
   serving with shrimp, you might not need much salt.)": conditional
   serving note; sauce rows complete, shrimp-free.
3. imp_2380cadece955cc7 Alfredo Sauce with Pasta, crustacean — **FP**.
   "Variation: Add cooked shrimp, crab or mushrooms" — optional
   variation, but MID-step ("Sprinkle with remaining cheese.
   Variation: …"), so the step-START commentary-prefix rule missed it.
4. imp_13e739367b505085 Spiced Pear Butter, dairy — **FP**. "cheese
   cloth" (two words) is cheesecloth, a tool; no dairy in the recipe.
5. imp_a07efbc761c35e16 Chocolate-Cinnamon Cake Roll, dairy — **CQ**.
   "spread with Cinnamon Whipped Cream; roll up" — the filling is
   whipped cream; no cream row. Hidden dairy.
6. imp_41bfceea6ba65b47 Corn Chowder, dairy — **CQ**. "add can cream
   style corn and can of milk" — no milk row.
7. imp_903a53ccc0b55219 Chocolate Rice Ruination, egg — **CQ**. "Beat
   in the egg yolks" — no egg row.
8. imp_0c0b6207064c5d15 Flowerpots (Baked Alaska), egg — **CQ**.
   Meringue from "Beat the egg whites" — rows are ice cream/sugar/
   vanilla only.
9. imp_b8e878e91861543a Bearnaise Sauce, egg — **CQ**. "whisk in egg
   yolks" — bearnaise IS emulsified egg yolk; no egg row.
10. imp_de9fdd7638765fc8 Cooked Salad Dressing, egg — **CQ**. "Beat
    the egg yolks slightly" — no egg row.
11. imp_58d0ea05ba705823 Deep Fried Fish, fish — **CQ**. Title dish;
    "Coat 2 pieces of fish with batter"; no fish row (b9e663c class).
12. imp_6cf61d5aa17d5f52 Peppered Fish in Herbed Butter, fish — **CQ**.
    Same class; no fish row.
13. imp_d3a91c593c3d55b2 Green and Gold Chowder, fish — **CQ**. "Flake
    fish, discarding skin and bones"; no fish row.
14. imp_ba2c9449969156af A Real Philly Cheesesteak, meat — **CQ**.
    "Cooking the steak:" — a cheesesteak with no steak row.
15. imp_caea496900545f7f Tagliolini w/ Truffles, meat — **CQ**. "Cook
    the fresh tagliolini in fresh Chicken Stock, not in water" — an
    explicit chicken-stock requirement, no row; also undisclosed pasta
    base. Non-vegetarian as instructed.
16. imp_3233766015ca524d Buttermilk Jalapeno Cornbread, meat — **FP**.
    "Can add drained corn, bacon, … etc. for a different taste" —
    optional user-initiated addition ("can add" phrasing not in the
    optional-variation list).
17. imp_d4597ae869735e8e Layer Cookies, nut — **CQ**. "Top with nuts"
    — no nut row.
18. imp_aeb6d9f6f5c55903 Deluxe Brownies, nut — **CQ**. "Stir in
    nuts" — no nut row.
19. imp_121294a381be5535 Microwave Honey Roasted Nuts, nut — **CQ**.
    The dish IS roasted nuts; rows are butter/honey/zest/cinnamon —
    the nuts themselves are missing. Flagrant incomplete row.
20. imp_8c7176ba96a35dce Chewy Chocolate Cookies, peanut — **CQ**.
    "Stir in peanut butter or chocolate chips" — rows contain NEITHER
    arm; the cookie requires one of them; peanut cannot be ruled out
    (rule-3 ambiguity class).
21. imp_73834906f18e553a Andouille in BBQ Sauce, peanut — **CQ**.
    "Saute … in peanut oil" — engine-visible peanut term, no oil row.
22. imp_bca827b64d08523e Beef Shreds w/ Green Pepper, peanut — **CQ**.
    "add to peanut oil" — same class. (Its crustacean flag was cleared
    by the round-1 garnishing-note rule; the peanut flag is genuine.)
23. imp_216295e7e97b5bdc Bean Curd With Broccoli, sesame — **CQ**.
    "Add wine, soy sauce and sesame oil" — no sesame row.
24. imp_fbf6565762c0590d Mabo Dofu, sesame — **CQ**. "sprinkle with
    the sesame oil and serve hot" — finishing oil is part of the dish;
    no sesame row.
25. imp_119bba669dca593d Fried Szechuan Chicken, sesame — **CQ**.
    "Marinate chicken with salt, five-spice powder and sesame oil" —
    no sesame row.
26. imp_ab6b542e34555631 Bottomless Chicken Soup Pot, soy — **FP**.
    "San Francisco: 3 cup fine egg noodles, … 2 tablespoons soy
    sauce…" — a named optional variation block (city add-ins);
    base-dish rows complete. Optional-variation class the current
    markers don't cover (city-name headers).
27. imp_068b162ec1445581 Pasta Soup Mix, soy — **CQ**. "Stir in …
    2 tsps. soy sauce" — part of the mainline cooking directions; no
    soy-sauce row (also undisclosed wheat via the new soy-sauce rule).
28. imp_d287af8d742e5d44 Katjang Sauce, soy — **FP**. "*Ketjap manis
    is a sweet Indonesian soy sauce…" — a definitional footnote for an
    ingredient the rows DO list ("ketjap manis"). Satisfier gap:
    ketjap manis is not a recognized soy satisfier.
29. imp_00efafa3c86e5b9e Beef Stroganoff with Dill, stock — **CQ**.
    "Add beef stock." / "Toss gently with chicken stock base" — no
    stock row, no animal row at all; undisclosed purchased stock.
30. imp_a76aa35639d85deb Borscht II, stock — **FP**. "keeping the
    broth at a simmer" — the broth is the pot liquor from simmering
    the LISTED beef stew meat; no purchased stock. Composite-arm gap:
    arm 2 requires a water row, but water is a commonly-unlisted item
    (the spec's own exclusion), so beef-simmering-liquid rows escape.
31. imp_2020aaedc3cf532a Lasagna Rollups, stock — **CQ**. "Stir in
    scalded milk, instant chicken broth…" — instant (purchased) broth,
    no row; animal row present but no water row, and the broth is not
    pot liquor.
32. imp_4206dd29ea5550fb Escalope of Salmon, stock — **CQ**. "add wine
    and fish stock" — added purchased fish stock, no row (hazard-class
    redundant with the listed salmon, but the row is genuinely
    incomplete; wine also undisclosed).
33. imp_6b64b4caa0125a71 Baked Acorn Squash, tree_nut — **CQ**.
    "Sprinkle with almonds" — no almond row.
34. imp_de9f4959d0855804 Cream Puff Paste, tree_nut — **CQ**. Praline
    filling made from almonds (embedded MasterCook block); no nut row.
35. imp_7895384b27835dfa Apple Strudel, tree_nut — **CQ**. "Mix apples
    with raisins, lemon rind, sugar, cinnamon, and almonds" — no
    almond row.
36. imp_329270d2ee78560a German Stuffed Veal Breast, wheat_gluten —
    **CQ**. "Mix ground meats, egg, bread crumbs…" — no bread row.
37. imp_748b6422ecbb5c7d Polish Sausage and Peppers, wheat_gluten —
    **FP**. "Serve the sausage and peppers and onions on French
    bread" — serving-vehicle in a step that BEGINS with "Serve"; the
    literal cue list ("serve on") missed the intervening words.
38. imp_654b6348a151563b Appetizer Sweet and Sour Meatballs,
    wheat_gluten — **CQ**. "Soak the bread in water" — bread is the
    meatball binder; no bread row.
39. imp_b79a7b507fc95c78 Calzones II, wheat_gluten — **CQ**. "Roll
    each biscuit between 2 sheets of floured wax paper" — refrigerated
    biscuit dough is the calzone wrapper; rows are fillings only.
40. imp_1b3530039f7a5ca3 Crock Pot Pork Casserole, meat — **CQ**.
    "Cut the pork into cubes" — title dish; no pork row.

**FP classes (new, each citable above):** (i) mid-step "Variation:"
markers (#3); (ii) optional-addition verb phrases "can add"/"can be
added … for a different taste" (#16); (iii) named variation-block
headers (#26); (iv) tool false-compound "cheese cloth" two-word form
(#4); (v) definitional footnotes for a listed ingredient — satisfier
gap `ketjap manis` (#28); (vi) step-initial "Serve …" serving-vehicle
steps the literal cue phrases miss (#37); (vii) intended-use
batter/sauce "dip/serve-with-alternatives" steps (#1, #2); (viii)
pot-liquor broth with a listed animal row but no listed water row
(#30 — the composite arm's water-row requirement contradicts the
spec's own "water is commonly unlisted" convention).

## Miss spot-check (n=15, seed 20260718) — 2 misses found (bar: 0)

- **MISS 1 — imp_635b6cd0fbd557ad "Hutspot"**: instructions "Add ribs,
  carrots and onions" and "When done take out bones and mash"; rows
  are carrots/onions/potatoes/water only. A vegetarian-looking row set
  whose dish contains ribs — exactly the engine-invisible hazard class.
  Vocabulary gap: bare `rib(s)` was deliberately excluded ("ribs of
  celery"), and `bones` is not a trigger. Spec bug per §3.
- **MISS 2 (class) — undisclosed wheat carriers `crust`/`pie shell`/
  `crepe`:** imp_15fe9cc27b96537b "Pumpkin-Pecan Pie" ("Pour into the
  unbaked pie shell" — no shell/flour row) and imp_3aee17154e8c59e9
  "Apple Raisin Cobbler Pie" ("Spoon into crust" — no crust row);
  imp_d63bae35bb3a55bb "Austrian Sweet Cheese Crepes" ("spread …
  filling on each crepe" — no crepe/flour row). The Prize Butter Tarts
  class, instructions-side. None of `crust`, `pie shell`, `shell`,
  `crepe` is a wheat_gluten trigger. Spec bug per §3.
- Rows checked and clean (no Tier A/B-class miss): imp_0a490b0819a15b81
  (crushed cookies — wheat disclosed via listed ladyfinger-cookie row,
  same hazard class), imp_2f284b242a8555f4, imp_1b67712639485a0f,
  imp_fe5e997cb47c553c (caramels — chocolate/caramel is the
  pre-existing PRECAUTIONARY backlog class, outside Tier A vocabulary;
  dairy category satisfied by listed evaporated milk/cream cheese),
  imp_5d7345ec55cd55d3 (generic "seeds" — not deterministically
  typeable), imp_98860ce03a2f5348, imp_60980e0a847f51d4,
  imp_76c9764c715b5af8 (instructions "milk" satisfied via the row-set's
  allergen-label OR-arm — designed leniency), imp_16baa175074c5e58
  (chocolate — precautionary class), imp_6fbf683033c953b3,
  imp_72681c74734b550b.

## Consequence

Round-2 fixes required (advisor ruling to specify exact forms): the
eight FP classes and two miss classes above. After round 2 the ceiling
will still be breached (~28% cannot fall below 12% via these deltas);
per spec §3 "maximum two revision rounds", the outcome is then the
pre-registered HUMAN GATE on the corpus itself.
