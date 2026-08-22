# EST-119 — corpus conversion (-sw arm)

`claude-opus-5` at effort **medium**, headless `claude -p`. Generated 2026-08-20T10:51:54.

## Whole corpus

| | |
|---|---|
| blobs converted | 5,448 of 11,609 |
| instance-file pairs | 15,126 |
| saved by content addressing | 23.3% |
| documentation records | 111,668 |
| anchored / unanchorable | 111,624 / 44 |
| model calls | 5,094 |
| input tokens (uncached) | 48,512,946 |
| cache-read tokens | 49,366,634 |
| output tokens | 10,938,764 |
| thinking tokens | 5,207,727 |
| model time | 31.48 h |
| nominal cost | $783.23 |
| median / p90 call | 9.8 s / 47.2 s |

Model time is the sum of per-call durations; at N-concurrent the clock time is roughly that divided by N.

## Per instance

| instance | blobs | done | records | anchored | unanch | output tok | model time h | $ |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| astropy__astropy-13398 | 503 | 473 | 13,354 | 13,345 | 9 | 1,350,928 | 3.74 | 90.19 |
| astropy__astropy-14365 | 510 | 486 | 13,614 | 13,614 | 0 | 1,396,043 | 3.79 | 93.11 |
| astropy__astropy-14598 | 509 | 485 | 13,611 | 13,611 | 0 | 1,393,266 | 3.78 | 93.01 |
| astropy__astropy-7336 | 399 | 386 | 10,435 | 10,434 | 1 | 1,045,911 | 2.84 | 70.84 |
| django__django-14631 | 853 | 632 | 8,565 | 8,560 | 5 | 833,661 | 2.65 | 63.46 |
| django__django-14787 | 854 | 655 | 9,226 | 9,208 | 18 | 891,318 | 2.81 | 67.05 |
| django__django-7530 | 843 | 712 | 9,659 | 9,655 | 4 | 911,708 | 2.69 | 68.49 |
| matplotlib__matplotlib-14623 | 748 | 697 | 9,430 | 9,430 | 0 | 894,282 | 2.94 | 75.82 |
| matplotlib__matplotlib-23299 | 770 | 763 | 13,269 | 13,266 | 3 | 1,299,050 | 3.86 | 98.52 |
| matplotlib__matplotlib-24970 | 777 | 721 | 10,361 | 10,361 | 0 | 1,056,183 | 3.24 | 83.40 |
| matplotlib__matplotlib-25311 | 769 | 739 | 12,901 | 12,900 | 1 | 1,290,367 | 3.88 | 96.48 |
| mwaskom__seaborn-3069 | 111 | 108 | 2,099 | 2,099 | 0 | 220,123 | 0.63 | 14.78 |
| pallets__flask-5014 | 33 | 33 | 510 | 510 | 0 | 37,690 | 0.11 | 3.58 |
| psf__requests-2931 | 83 | 71 | 3,402 | 3,394 | 8 | 224,399 | 0.59 | 13.40 |
| pydata__xarray-4356 | 96 | 50 | 1,428 | 1,428 | 0 | 137,967 | 0.37 | 11.23 |
| pydata__xarray-7229 | 115 | 55 | 699 | 699 | 0 | 60,418 | 0.18 | 5.91 |
| pylint-dev__pylint-6528 | 405 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| pytest-dev__pytest-10051 | 86 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| pytest-dev__pytest-5262 | 74 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| scikit-learn__scikit-learn-10297 | 496 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| scikit-learn__scikit-learn-13142 | 544 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| scikit-learn__scikit-learn-15100 | 534 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| scikit-learn__scikit-learn-25102 | 619 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sphinx-doc__sphinx-11445 | 174 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sphinx-doc__sphinx-8475 | 188 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sympy__sympy-13551 | 675 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sympy__sympy-16597 | 752 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sympy__sympy-20916 | 845 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sympy__sympy-22714 | 883 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
| sympy__sympy-23824 | 878 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.00 |
