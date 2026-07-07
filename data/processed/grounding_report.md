# Grounding report

## Corpus-wide summary
- total recipes processed: 4263
- grounded: 10 (0.2%)
- partial: 2527 (59.3%)
- ungrounded: 1726 (40.5%)

## Seed tag-vs-computed comparison (25 recipes)

| recipe_id | title | status | coverage | tag kcal | computed kcal | ratio |
|---|---|---|---|---|---|---|
| r_001 | Mediterranean Chicken Rice Bowl | grounded | 100% | 610 | 590 | 0.97x |
| r_002 | Thai Peanut Tofu Stir Fry | grounded | 100% | 540 | 605 | 1.12x |
| r_003 | Mexican Turkey Black Bean Skillet | partial | 88% | 520 | 623 | 1.20x |
| r_004 | Italian Lentil Tomato Pasta | partial | 88% | 590 | 923 | 1.56x |
| r_005 | Japanese Salmon Sushi Bowl | grounded | 100% | 650 | 734 | 1.13x |
| r_006 | American Egg White Veggie Omelet | partial | 86% | 330 | 245 | 0.74x |
| r_007 | Indian Chickpea Spinach Curry | partial | 62% | 560 | 375 | 0.67x |
| r_008 | Mediterranean Quinoa Chickpea Salad | grounded | 100% | 480 | 823 | 1.72x **[RAW/COOKED BLOWUP]** |
| r_009 | Dairy-Free Chicken Fajita Plate | partial | 88% | 620 | 669 | 1.08x |
| r_010 | Gluten-Free Turkey Meatballs | partial | 62% | 500 | 518 | 1.04x |
| r_011 | Thai Basil Shrimp Rice | partial | 88% | 470 | 417 | 0.89x |
| r_012 | American Turkey Sweet Potato Chili | partial | 86% | 570 | 616 | 1.08x |
| r_013 | Japanese Miso Tofu Soup Bowl | grounded | 100% | 410 | 426 | 1.04x |
| r_014 | Indian Chicken Tikka Lettuce Bowls | partial | 88% | 580 | 324 | 0.56x |
| r_015 | Mexican Vegan Burrito Bowl | partial | 88% | 530 | 601 | 1.13x |
| r_016 | Italian Caprese Chicken | grounded | 100% | 620 | 856 | 1.38x |
| r_017 | Mediterranean Lentil Soup | grounded | 100% | 430 | 572 | 1.33x |
| r_018 | American Greek Yogurt Protein Parfait | partial | 83% | 420 | 509 | 1.21x |
| r_019 | Thai Green Curry Chicken | partial | 88% | 680 | 638 | 0.94x |
| r_020 | Japanese Chicken Teriyaki Bowl | partial | 88% | 590 | 553 | 0.94x |
| r_021 | Indian Paneer Pea Curry | partial | 75% | 640 | 611 | 0.96x |
| r_022 | Mediterranean Tuna White Bean Salad | grounded | 100% | 450 | 466 | 1.04x |
| r_023 | American Beef Quinoa Stuffed Peppers | grounded | 100% | 610 | 1039 | 1.70x **[RAW/COOKED BLOWUP]** |
| r_024 | Mexican Shrimp Taco Salad | partial | 88% | 500 | 470 | 0.94x |
| r_025 | Italian White Bean Zucchini Stew | grounded | 100% | 420 | 460 | 1.09x |

## Flags: raw/cooked-scale blowup (>1.6x)
- **r_008** (Mediterranean Quinoa Chickpea Salad): ratio 1.72x
- **r_023** (American Beef Quinoa Stuffed Peppers): ratio 1.70x

## Flags: implausible kcal/serving band (<20 or >2000)
None.

## Known residuals (investigated, deliberately not fixed further)

- **jasmine rice / basmati rice**: No variety-specific Foundation/SR Legacy/Survey record exists for either (confirmed live, even with the query augmented by the declared 'cooked' state) -- only generic 'Rice, white, cooked' entries exist. Rather than silently substitute a different variety, jasmine rice stays on its Branded match (JASMINE COOKED RICE, JASMINE, ~225 kcal/100g -- notably above a true ~130 kcal/100g, likely includes added oil/seasoning) and basmati stays UNGROUNDED. Not preparation-fixable.
- **zucchini**: FDC's canonical zucchini record is filed under 'Squash' (e.g. 'Squash, summer, green, zucchini, includes skin, raw'), not 'Zucchini' -- the relevance check's head-noun rule correctly refuses to treat that as the same food as a bare 'zucchini' query without a synonym table it doesn't have. Resolves to a Branded 'Zucchini, pickled' (~35 kcal/100g) instead of raw (~21 kcal/100g). Not preparation-fixable.
- **shrimp / tomato sauce / chili powder / ginger**: Explicitly excluded via usda_client._KNOWN_UNRELIABLE_QUERIES -- shrimp and tomato sauce reliably resolve to a wrong-form match with no preparation declaration able to gate it (a sauce/seafood has no honest raw/cooked/canned state); chili powder and ginger's only reachable Branded record reports 0 kcal/100g, a data defect rather than a matching problem. All four render UNGROUNDED rather than a confidently wrong number.
- **olive oil**: Deterministically matches 'Oil, corn, peanut, and olive' (SR Legacy) instead of pure olive oil -- wrong specific product, but zero practical calorie impact (~884-900 kcal/100g either way, consistent with any pure fat). Left as-is.
- **general case: undeclared-preparation same-food-wrong-state matches**: The `preparation` field and the relevance check only cover ingredients that declare a state. Any ingredient without one (i.e. everything outside the seeds' explicitly-audited set) can still land on a processed/wrong-state USDA record purely by dataType-tier order -- this was the root cause behind chicken breast, ground turkey, corn, and tofu before they were individually audited and fixed for the 25 seeds. Unaudited for the imported corpus at large -- see docs/ROADMAP.md.

## Per-ingredient grounding detail

### r_001 -- Mediterranean Chicken Rice Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 180.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| Greek yogurt | True | 61.8 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_002 -- Thai Peanut Tofu Stir Fry (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tofu | True | 150.0 | matched: Tofu, raw, firm, prepared with calcium sulfate (SR Legacy) |
| rice noodles | True | 120.0 | matched: Rice noodles, cooked (SR Legacy) |
| broccoli | True | 80.0 | matched: Broccoli, raw (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| peanut butter | True | 30.0 | matched: Peanut butter (Survey (FNDDS)) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |

### r_003 -- Mexican Turkey Black Bean Skillet (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 170.0 | matched: Turkey, Ground, raw (SR Legacy) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 80.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| coriander | False | 5.0 | ungrounded: no USDA match |

### r_004 -- Italian Lentil Tomato Pasta (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| whole wheat pasta | True | 100.0 | matched: Pasta, whole grain, 51% whole wheat, remaining unenriched semolina, dry (SR Legacy) |
| lentils | True | 100.0 | matched: Lentils, dry (Foundation) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| parmesan | False | 20.0 | ungrounded: no USDA match |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_005 -- Japanese Salmon Sushi Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| salmon | True | 170.0 | matched: SALMON (Branded) |
| white rice | True | 180.0 | matched: Rice, cooked, NFS (Survey (FNDDS)) |
| cucumber | True | 60.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| edamame | True | 60.0 | matched: Edamame, frozen, prepared (SR Legacy) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| nori | True | 3.0 | matched: NORI (Branded) |
| sesame seeds | True | 6.0 | matched: Seeds, sesame seeds, whole, dried (SR Legacy) |

### r_006 -- American Egg White Veggie Omelet (partial, coverage 86%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| egg whites | True | 150.0 | matched: Eggs, Grade A, Large, egg white (Foundation) |
| whole egg | False | n/a | ungrounded: amount/unit not convertible to grams |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| mushroom | True | 40.0 | matched: Mushroom, beech (Foundation) |
| bell pepper | True | 59.5 | matched: Peppers, bell, green, raw (Foundation) |
| cheddar cheese | True | 30.0 | matched: Cheese, cheddar (Foundation) |
| green onion | True | 10.0 | matched: Onions, young green, tops only (SR Legacy) |

### r_007 -- Indian Chickpea Spinach Curry (partial, coverage 62%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chickpeas | True | 150.0 | matched: Chickpeas, from canned, fat added (Survey (FNDDS)) |
| spinach | True | 60.0 | matched: Spinach, baby (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| ginger | False | 5.0 | ungrounded: no USDA match |
| coconut milk | False | 98.0 | ungrounded: no USDA match for declared state 'canned' |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |

### r_008 -- Mediterranean Quinoa Chickpea Salad (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| quinoa | True | 90.0 | matched: Quinoa, uncooked (SR Legacy) |
| chickpeas | True | 100.0 | matched: Chickpeas, from canned, fat added (Survey (FNDDS)) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| feta cheese | True | 40.0 | matched: FETA (Branded) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| parsley | True | 5.0 | matched: Parsley, fresh (SR Legacy) |

### r_009 -- Dairy-Free Chicken Fajita Plate (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 180.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| onion | True | 110.0 | matched: Onions, raw (SR Legacy) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| black beans | True | 100.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| coriander | False | 5.0 | ungrounded: no USDA match |

### r_010 -- Gluten-Free Turkey Meatballs (partial, coverage 62%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 200.0 | matched: Turkey, Ground, raw (SR Legacy) |
| whole egg | False | n/a | ungrounded: amount/unit not convertible to grams |
| almond flour | True | 30.0 | matched: Flour, almond (Foundation) |
| tomato sauce | False | 100.0 | ungrounded: no USDA match |
| zucchini noodles | True | 150.0 | matched: ZUCCHINI NOODLES, ZUCCHINI (Branded) |
| parmesan | False | 20.0 | ungrounded: no USDA match |
| garlic | True | 5.0 | matched: Garlic, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |

### r_011 -- Thai Basil Shrimp Rice (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| shrimp | False | 180.0 | ungrounded: no USDA match |
| jasmine rice | True | 150.0 | matched: JASMINE COOKED RICE, JASMINE (Branded) |
| green beans | True | 60.0 | matched: Green beans, raw (Survey (FNDDS)) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |

### r_012 -- American Turkey Sweet Potato Chili (partial, coverage 86%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 170.0 | matched: Turkey, Ground, raw (SR Legacy) |
| sweet potato | True | 150.0 | matched: SWEET POTATO (Branded) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| chili powder | False | 5.0 | ungrounded: no USDA match |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |

### r_013 -- Japanese Miso Tofu Soup Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tofu | True | 120.0 | matched: Tofu, raw, firm, prepared with calcium sulfate (SR Legacy) |
| miso paste | True | 20.0 | matched: MISO PASTE (Branded) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| mushroom | True | 40.0 | matched: Mushroom, beech (Foundation) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| green onion | True | 10.0 | matched: Onions, young green, tops only (SR Legacy) |
| seaweed | True | 5.0 | matched: Seaweed, agar, raw (SR Legacy) |
| soy sauce | True | 11.0 | matched: Soy sauce (Survey (FNDDS)) |

### r_014 -- Indian Chicken Tikka Lettuce Bowls (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| Greek yogurt | True | 61.8 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| lettuce | True | 60.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| cucumber | True | 60.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |
| garam masala | True | 5.0 | matched: GARAM MASALA (Branded) |
| lemon | True | 20.0 | matched: Lemon, raw (Survey (FNDDS)) |

### r_015 -- Mexican Vegan Burrito Bowl (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 80.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| lettuce | True | 40.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| avocado | True | 112.5 | matched: Avocados, raw, California (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| coriander | False | 5.0 | ungrounded: no USDA match |

### r_016 -- Italian Caprese Chicken (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| mozzarella | True | 60.0 | matched: MOZZARELLA (Branded) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| balsamic vinegar | True | 15.0 | matched: Vinegar, balsamic (SR Legacy) |
| olive oil | True | 9.1 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| zucchini | True | 100.0 | matched: Zucchini, pickled (Survey (FNDDS)) |
| quinoa | True | 80.0 | matched: Quinoa, uncooked (SR Legacy) |

### r_017 -- Mediterranean Lentil Soup (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| lentils | True | 100.0 | matched: Lentils, dry (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| celery | True | 40.0 | matched: Celery, raw (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| lemon | True | 10.0 | matched: Lemon, raw (Survey (FNDDS)) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_018 -- American Greek Yogurt Protein Parfait (partial, coverage 83%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| Greek yogurt | True | 206.0 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| berries | False | 80.0 | ungrounded: no USDA match |
| oats | True | 40.0 | matched: Oats, raw (Survey (FNDDS)) |
| chia seeds | True | 15.0 | matched: Chia seeds, dry, raw (Foundation) |
| honey | True | 21.3 | matched: Honey (SR Legacy) |
| almonds | True | 15.0 | matched: Almonds, flavored (Survey (FNDDS)) |

### r_019 -- Thai Green Curry Chicken (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| coconut milk | False | 147.0 | ungrounded: no USDA match for declared state 'canned' |
| green curry paste | True | 20.0 | matched: GREEN CURRY PASTE (Branded) |
| zucchini | True | 80.0 | matched: Zucchini, pickled (Survey (FNDDS)) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| jasmine rice | True | 150.0 | matched: JASMINE COOKED RICE, JASMINE (Branded) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |

### r_020 -- Japanese Chicken Teriyaki Bowl (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| white rice | True | 180.0 | matched: Rice, cooked, NFS (Survey (FNDDS)) |
| broccoli | True | 70.0 | matched: Broccoli, raw (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| soy sauce | True | 22.0 | matched: Soy sauce (Survey (FNDDS)) |
| honey | True | 14.2 | matched: Honey (SR Legacy) |
| garlic | True | 5.0 | matched: Garlic, raw (Foundation) |
| ginger | False | 5.0 | ungrounded: no USDA match |

### r_021 -- Indian Paneer Pea Curry (partial, coverage 75%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| paneer | True | 150.0 | matched: PANEER (Branded) |
| peas | True | 100.0 | matched: PEAS (Branded) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| ginger | False | 5.0 | ungrounded: no USDA match |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |

### r_022 -- Mediterranean Tuna White Bean Salad (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tuna | True | 150.0 | matched: TUNA (Branded) |
| white beans | True | 120.0 | matched: Beans, white, mature seeds, canned (SR Legacy) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| red onion | True | 50.0 | matched: Onions, red, raw (Foundation) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| parsley | True | 5.0 | matched: Parsley, fresh (SR Legacy) |

### r_023 -- American Beef Quinoa Stuffed Peppers (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground beef | True | 180.0 | matched: Beef, ground (Survey (FNDDS)) |
| quinoa | True | 80.0 | matched: Quinoa, uncooked (SR Legacy) |
| bell pepper | True | 238.0 | matched: Peppers, bell, green, raw (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| cheddar cheese | True | 40.0 | matched: Cheese, cheddar (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |

### r_024 -- Mexican Shrimp Taco Salad (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| shrimp | False | 180.0 | ungrounded: no USDA match |
| lettuce | True | 60.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| black beans | True | 100.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 70.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| tortilla strips | True | 30.0 | matched: TORTILLA STRIPS, TORTILLA (Branded) |

### r_025 -- Italian White Bean Zucchini Stew (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| white beans | True | 150.0 | matched: Beans, white, mature seeds, canned (SR Legacy) |
| zucchini | True | 120.0 | matched: Zucchini, pickled (Survey (FNDDS)) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
