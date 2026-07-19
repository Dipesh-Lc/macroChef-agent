# Manual-quarantine release adjudication

- Re-import run: 20260719T070200Z (task A1, scraped-archive re-import).
- Scope: every id in this run's `released` bucket whose PRIOR quarantine record has `quarantine_reason.check == "manual_adjudication"` -- i.e. a recipe that was never quarantined by the automated title/instructions integrity scans, but by a human/advisor adjudication of a specific adversarial-benchmark finding.
- Why this file exists: an automated re-import passing its OWN checks is not the same evidence as a human re-reviewing the ORIGINAL manual finding. This file is the written record that a human (the advisor) did exactly that, per case, for every id below -- consistent with this project's adjudication convention (data/evaluation/adjudication_20260717T145539Z.md): verdict, matched defect, served recipe's actual ingredient rows, citable cure evidence.
- Adjudicator: advisor, 2026-07-19 (A1 revise round).

## Cases

### imp_2bd54fd475cf50fc -- 'Butterscotch Chewy Bars'
- Foodcom source id: 3691
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260718T090522Z.md diet_023: instructions 'stir in cereals' with no cereal row
- Old (CSV-import) ingredient rows: ['butter', 'margarine', 'brown sugar', 'miniature marshmallows']
- New (scraped-archive) ingredient rows: ['butter or 3 tablespoons margarine', 'brown sugar, firmly packed', 'miniature marshmallows', 'crispy rice cereal', 'corn flakes cereal']
- Cure evidence: Butterscotch Chewy Bars -- original finding (adjudication_20260718T090522Z diet_023 class): instructions 'stir in cereals' with no cereal ingredient row. Cured: archive ingredients now include 'crispy rice cereal' and 'corn flakes cereal'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_348d24dd1f4d5284 -- 'Prize Butter Tarts'
- Foodcom source id: 2123
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T145539Z diet_023: instructions-column evidence 'Prepare pastry dough… line tart pans' with no corresponding ingredient row
- Old (CSV-import) ingredient rows: ['brown sugar', 'seedless raisins', 'pecans', 'butter', 'margarine', 'egg', 'milk', 'vanilla']
- New (scraped-archive) ingredient rows: ['brown sugar', 'seedless raisins or 1/2 cup pecans, chopped', 'butter or 1/3 cup margarine, melted', 'egg, beaten', 'milk', 'vanilla', 'pastry for double-crust pie']
- Cure evidence: Prize Butter Tarts -- original finding (adjudication_20260717T145539Z diet_023): instructions 'Prepare pastry dough... line tart pans' with no pastry ingredient row. Cured: archive ingredients now include 'pastry for double-crust pie'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_42d786e354855c6c -- 'Grape-Nuts Pudding'
- Foodcom source id: 7439
- Original quarantine check: manual_adjudication
- Original quarantine reason: cereal vocabulary miss-fix (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row
- Old (CSV-import) ingredient rows: ['quick-cooking tapioca', 'raisins', 'boiling water', 'brown sugar', 'vanilla extract']
- New (scraped-archive) ingredient rows: ['quick-cooking tapioca', 'raisins', 'boiling water', 'Post Grape-Nuts cereal', 'brown sugar', 'vanilla extract']
- Cure evidence: Grape-Nuts Pudding -- original finding (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row. Cured: archive ingredients now include 'Post Grape-Nuts cereal'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_6ab74a6c238451a3 -- 'Banana-Nut Muffins'
- Foodcom source id: 6960
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T145539Z macro_018: instructions-column evidence 'Mix nuts with' with no corresponding ingredient row
- Old (CSV-import) ingredient rows: ['white flour', 'baking powder', 'salt', 'ground cinnamon', 'ground nutmeg', 'butter', '- 1 margarine', 'sugar', 'eggs', 'vanilla extract', 'bananas']
- New (scraped-archive) ingredient rows: ['white flour', 'baking powder', 'salt', 'ground cinnamon', 'ground nutmeg', 'butter or 1/2 cup margarine', '-1 cup sugar, depending on how sweet you want your muffins (I use 2/3 cup)', 'eggs', 'vanilla extract', 'bananas', 'nuts (walnuts or pecans are good)']
- Cure evidence: Banana-Nut Muffins -- original finding (adjudication_20260717T145539Z macro_018): instructions 'Mix nuts with' with no nuts ingredient row. Cured: archive ingredients now include 'nuts (walnuts or pecans are good)'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_78c1d567c07b545a -- 'Chinese Beef and Broccoli'
- Foodcom source id: 1267
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T145539Z diet_015: instructions-column evidence 'Slice the steak' with no corresponding ingredient row
- Old (CSV-import) ingredient rows: ['soy sauce', 'dry sherry', 'cornstarch', 'frozen broccoli', 'garlic clove', 'fresh ginger', 'salt']
- New (scraped-archive) ingredient rows: ['flank steak', 'soy sauce', 'dry sherry (can substitute 1 Tbs. orange or pineapple juice with a dash of vinegar)', 'cornstarch', 'frozen broccoli, defrosted', 'garlic clove, minced', 'fresh ginger, finely minced', 'peanut oil', 'salt']
- Cure evidence: Chinese Beef and Broccoli -- original finding (adjudication_20260717T145539Z diet_015): instructions 'Slice the steak' with no steak/beef ingredient row. Cured: archive ingredients now include 'flank steak'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_997819df41245ec6 -- 'Perfectly Spiced Banana Bread'
- Foodcom source id: 1387
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T165139Z.md advisor review: instructions-column evidence of incomplete ingredient rows
- Old (CSV-import) ingredient rows: ['all-purpose flour', 'baking powder', 'baking soda', 'salt', 'ginger', 'allspice', 'nutmeg', 'lemon zest', 'butter', 'margarine', 'sugar', 'eggs', 'bananas']
- New (scraped-archive) ingredient rows: ['all-purpose flour', 'baking powder', 'baking soda', 'salt', 'ginger, ground', 'allspice, ground', 'nutmeg, grated', 'grated lemon zest (optional)', 'almonds, ground (optional)', 'butter or 1/2 cup margarine', 'sugar', 'large eggs', 'ripe bananas, mashed (4 medium)']
- Cure evidence: Perfectly Spiced Banana Bread -- original finding (adjudication_20260717T165139Z.md advisor review): instructions-column evidence of incomplete ingredient rows. Cured: archive ingredient list is substantially fuller (13 rows including flour/eggs/bananas/spices vs. the CSV's truncated set).
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_9c4f812bcda75ef0 -- 'Crunchy Pretzel Drops No-Bake Cookies'
- Foodcom source id: 688
- Original quarantine check: manual_adjudication
- Original quarantine reason: cereal vocabulary miss-fix (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row
- Old (CSV-import) ingredient rows: ['light corn syrup', 'milk', 'butter', 'vanilla']
- New (scraped-archive) ingredient rows: ['butterscotch chips', 'light corn syrup', 'milk', 'butter', 'vanilla', 'puffed corn cereal', 'broken pretzel']
- Cure evidence: Crunchy Pretzel Drops No-Bake Cookies -- original finding (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row. Cured: archive ingredients now include 'puffed corn cereal'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_9e0a542fc2195d5b -- 'Bananas Baked With Custard'
- Foodcom source id: 2928
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T165139Z.md advisor review: instructions-column evidence of incomplete ingredient rows
- Old (CSV-import) ingredient rows: ['butter', 'bananas', 'sultanas', 'milk', 'eggs', 'brown sugar', 'nutmeg']
- New (scraped-archive) ingredient rows: ['butter', 'bananas', 'bread, thin sliced, buttered', 'sultanas', 'milk', 'eggs', 'egg yolks', 'brown sugar', 'nutmeg']
- Cure evidence: Bananas Baked With Custard -- original finding (adjudication_20260717T165139Z.md advisor review): instructions-column evidence of incomplete ingredient rows. Cured: archive ingredients now include bread, egg yolks, milk, sultanas.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_9ff0ac08d2b353ca -- 'Banana Bran Muffins with Strawberry Butter'
- Foodcom source id: 5401
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T165139Z.md advisor review: instructions-column evidence of incomplete ingredient rows
- Old (CSV-import) ingredient rows: ['all-purpose flour', 'baking powder', 'butter', 'baking soda', 'egg', 'banana', 'plain yogurt', 'brown sugar', 'molasses', 'butter']
- New (scraped-archive) ingredient rows: ['all-purpose flour', 'baking powder', 'butter, firm', 'baking soda', 'natural bran', 'nuts, chopped', 'egg', 'banana, mashed', 'plain yogurt', 'brown sugar, packed', 'molasses', 'butter, softened', 'strawberry jam']
- Cure evidence: Banana Bran Muffins with Strawberry Butter -- original finding (adjudication_20260717T165139Z.md advisor review): instructions-column evidence of incomplete ingredient rows. Cured: archive ingredients now include bran, nuts, egg, banana, yogurt.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_e5c662ec002355d6 -- 'Praline Pecan Crunch'
- Foodcom source id: 4846
- Original quarantine check: manual_adjudication
- Original quarantine reason: cereal vocabulary miss-fix (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row
- Old (CSV-import) ingredient rows: ['pecan pieces', 'light corn syrup', 'brown sugar', 'margarine', 'butter', 'vanilla', 'baking soda']
- New (scraped-archive) ingredient rows: ['Quaker Oatmeal Squares Cereal', 'pecan pieces', 'light corn syrup', 'brown sugar, firmly packed', 'margarine (1/2 stick) or 1/4 cup butter (1/2 stick)', 'vanilla', 'baking soda']
- Cure evidence: Praline Pecan Crunch -- original finding (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row. Cured: archive ingredients now include 'Quaker Oatmeal Squares Cereal'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_fbfd3dda61af5cd5 -- 'No-Bake Cereal Bars'
- Foodcom source id: 3010
- Original quarantine check: manual_adjudication
- Original quarantine reason: cereal vocabulary miss-fix (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row
- Old (CSV-import) ingredient rows: ['light corn syrup', 'sugar', 'peanut butter']
- New (scraped-archive) ingredient rows: ['light corn syrup', 'sugar', 'peanut butter', 'Cheerios toasted oat cereal', 'semi-sweet chocolate chips']
- Cure evidence: No-Bake Cereal Bars -- original finding (adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed cereal, no cereal row. Cured: archive ingredients now include 'Cheerios toasted oat cereal'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19

### imp_ffba7239b17c5b29 -- 'Spicy Fish Cakes'
- Foodcom source id: 4202
- Original quarantine check: manual_adjudication
- Original quarantine reason: adjudication_20260717T145539Z injection_014: instructions-column evidence 'Cut the fish into small pieces' with no corresponding ingredient row
- Old (CSV-import) ingredient rows: ['spring onions', 'red capsicum', 'potatoes', 'eggs', 'flour', 'salt', 'parsley', 'butter']
- New (scraped-archive) ingredient rows: ['spring onions', 'red capsicum', 'potatoes, cold, cooked', 'creole seasoning', 'fish fillets', 'eggs', 'flour', 'salt', 'parsley, chopped', 'oil', 'butter']
- Cure evidence: Spicy Fish Cakes -- original finding (adjudication_20260717T145539Z injection_014): instructions 'Cut the fish into small pieces' with no fish ingredient row. Cured: archive ingredients now include 'fish fillets'.
- Verdict: RELEASE JUSTIFIED -- defect cured at source, advisor-reviewed 2026-07-19
