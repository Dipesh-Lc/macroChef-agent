# Sample-audit adjudication — instructions-integrity run 20260718T001212Z (round 2, final round)

- Sample: n=40, seed 20260719, stratified per spec §3, drawn from the
  1156-row flagged set (report 20260718T001212Z). Adjudicator:
  orchestrator session, 2026-07-18.
- **RESULT: 36 CORRECT_QUARANTINE / 4 FALSE_POSITIVE → measured
  precision 90.0%.** The ≤2/40 bar is still formally breached, but the
  spec's maximum of two revision rounds is exhausted; per the
  pre-registered path (spec §3 + the advisor's round-2 pre-statement),
  the outcome is the corpus HUMAN GATE, with this measured precision
  and the residual FP classes below attached as evidence. No further
  suppression rounds are run — chasing the ceiling or the sample bar
  past the pre-registered limit would be results-driven tuning.
- Miss spot-check (n=15, seed 20260719): no mechanical miss; one
  borderline leniency finding (below).

## FALSE_POSITIVE cases (4) — residual FP classes for the gate brief

1. imp_f075b353b18f5be7 Thai Fish Curry, crustacean — "The mild spice
   paste is also great used as a base for chicken and shrimp curries."
   Alternative-use commentary; the dish itself is a sea-bass curry with
   complete rows. Class: alternative-use notes without a recognized cue.
2. imp_126588c694d85ab7 Welsh Rarebit, meat — "slices of ham and
   tomatoes may be added." Class: "may be added" optional phrasing not
   in the optional-variation list.
3. imp_c280c19ca3cd52e3 Roasted Vegetables, soy — "Note 1: You can
   roast a piece of fish or chicken (or marinated tofu)…" Class:
   numbered commentary markers ("Note 1:" — the marker regex requires
   `notes?:` with no intervening token) plus "you can" optional
   phrasing.
4. imp_91551b3711895e7d Chicken Stock, stock — the recipe's PRODUCT is
   stock made from the listed giblets/vegetables; "the stock" is
   self-referential to the yield, not an undisclosed ingredient.
   Class: self-referential yield mentions in from-scratch stock
   recipes.

## CORRECT_QUARANTINE cases (36) — abbreviated citations

crustacean: imp_09c936ec1c8754a1 (Crabby Quiche Pie — layers crab, no
crab row), imp_a9560c6c0bc05ec1 (mixes rice with shrimps, no shrimp
row). dairy: imp_9fc15b49deb55beb (beats whipping cream, no cream
row), imp_5b8b3482fed9587a (folds in whipped cream, no row),
imp_6e9b1a934cc35b5d (sautés in butter, no butter row). egg:
imp_4b5df4868cff514b, imp_5638d042bdcf5bd6, imp_b3e92285283c5256,
imp_475be60e7657505d (all: egg yolks/whites used, no egg row). fish:
imp_06bc46d645225dc0, imp_64050c116e505581, imp_cfe4b7fa882c50e6 (all:
fish dishes, no fish row). meat: imp_8f2b04bbe4235824 (steak dish, no
steak row), imp_0abd6157700056f6 (stuffing prepared inside a
chicken/turkey cavity — integral to preparation, not optional serving;
vegetarian-visible), imp_e9228644b70c53a4 (beef jerky, no beef row —
the item-12 Filet-Mignon class working as designed). nut:
imp_bfc684a6a91c510c, imp_1612bdf5e4fb527d, imp_4fb94d65201b51b1
(nuts added, no nut row). peanut: imp_bca827b64d08523e,
imp_686276c94ca45d6a, imp_ace7f2163a7c57f6 (peanut oil / peanut
butter, no row). sesame: imp_27ac42cfb3075ae1, imp_ed9c0041f5425d3a,
imp_216295e7e97b5bdc (sesame oil, no row). soy: imp_63414a2d206e57f7
(adds soy sauce + sesame oil, neither listed), imp_068b162ec1445581
(mainline soy sauce, no row). stock: imp_5fc1b44e427b5701 (rice cooked
in stock, no stock/animal row), imp_890db718f4dd5334 (Oxtail Soup with
no oxtail row — stock made from unlisted oxtails),
imp_a09a86ba51875f19 ("Add a little stock", no row — arm 3 correctly
kept it). tree_nut: imp_bd59363a8ddc5844, imp_69ef9922e06f5e53,
imp_7065e908d0bd5820 (almonds added, no row). wheat_gluten:
imp_13a3c9f8e0635817 (rolls dough for a hero, no dough/flour row),
imp_ec7fcb0914b35db7 (unbaked pie shell, no shell/flour row — new
item-11 trigger), imp_4828bc7cc2b65262 (a cake with no flour or mix
row), imp_639d7b4c10a75054 (bread crumbs, no bread row).

## Miss spot-check (n=15, seed 20260719)

No mechanical miss. One borderline leniency finding, recorded for the
gate brief (not a round-2 regression; pre-existing design):
imp_4e524f5f9f8759a9 Sesame Chicken Cutlets — "combine bread crumbs
and sesame seeds"; no bread-class row, but the listed `soy sauce` row
satisfies the wheat_gluten category because dual-category terms
satisfy ANY mention of their category. Same structural class as the
documented residual imp_3aee17154e8c59e9. A future scoping decision
(dual-category terms satisfying only their own occurrences) is a
candidate round-3 ruling if the human continues with this corpus.

## Consequence

Estimated true-corruption fraction of the imported corpus:
28.58% flagged × 90.0% measured precision ≈ **25.7% of 4,045 rows
(~1,040 rows) genuinely name a safety-relevant ingredient their
ingredient list omits.** Maximum revision rounds exhausted; ceiling
(12%) still breached. Per the pre-registered spec §3 path this is now
a HUMAN GATE: mass-quarantine vs corpus swap vs claim narrowing.
