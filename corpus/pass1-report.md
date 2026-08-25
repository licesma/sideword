# Pass 1 report (strip cache)

Generated 2026-08-25T02:28:39+00:00 · wall 45.8 s · jobs 10 · directives sha256 `f5e1ed55296a` · stripper `6d90ee8b66b2`

Instances 30 · blob refs 15,126 · unique blobs 11,609 · on disk before run 0

## Totals over unique blobs

| files | comments removed | docstrings removed | doctest kept | docstrings kept | directives kept | stray kept | unresolved | parse errors | AST failures | errors | `__doc__` files | bytes before | bytes after | lines before | lines after |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 11,609 | 298,429 | 77,032 | 20,719 | 392 | 8,605 | 732 | 0 | 0 | 0 | 0 | 948 | 178,415,565 | 137,226,992 | 4,778,548 | 3,801,528 |

## Per repo (unique blobs)

| repo | inst | unique blobs | blob refs | reuse | comments removed | docstrings removed | doctest kept | docstrings kept | directives kept | stray kept | unresolved | parse errors | AST failures | `__doc__` files | bytes before | bytes after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astropy/astropy | 4 | 1,341 | 1,921 | 30.2% | 45,214 | 12,395 | 790 | 318 | 581 | 234 | 0 | 0 | 0 | 164 | 20,695,238 | 13,052,746 |
| django/django | 3 | 1,558 | 2,550 | 38.9% | 26,504 | 8,960 | 76 | 0 | 382 | 2 | 0 | 0 | 0 | 21 | 11,857,913 | 8,808,122 |
| matplotlib/matplotlib | 4 | 2,445 | 3,064 | 20.2% | 71,968 | 16,524 | 210 | 22 | 1,439 | 68 | 0 | 0 | 0 | 85 | 24,328,880 | 14,573,673 |
| mwaskom/seaborn | 1 | 108 | 111 | 2.7% | 2,317 | 532 | 1 | 16 | 55 | 0 | 0 | 0 | 0 | 9 | 1,082,079 | 796,077 |
| pallets/flask | 1 | 33 | 33 | 0.0% | 657 | 265 | 0 | 0 | 88 | 7 | 0 | 0 | 0 | 2 | 337,291 | 171,067 |
| psf/requests | 1 | 83 | 83 | 0.0% | 4,825 | 355 | 19 | 0 | 35 | 0 | 0 | 0 | 0 | 1 | 803,241 | 590,258 |
| pydata/xarray | 2 | 199 | 211 | 5.7% | 4,837 | 1,940 | 324 | 5 | 221 | 1 | 0 | 0 | 0 | 20 | 4,265,689 | 3,224,110 |
| pylint-dev/pylint | 1 | 399 | 405 | 1.5% | 3,095 | 1,223 | 7 | 5 | 204 | 67 | 0 | 0 | 0 | 6 | 1,620,509 | 1,281,705 |
| pytest-dev/pytest | 2 | 153 | 160 | 4.4% | 3,046 | 1,449 | 9 | 1 | 193 | 15 | 0 | 0 | 0 | 6 | 1,830,669 | 1,353,180 |
| scikit-learn/scikit-learn | 4 | 1,870 | 2,193 | 14.7% | 42,326 | 9,947 | 1,157 | 5 | 1,479 | 154 | 0 | 0 | 0 | 487 | 24,289,948 | 15,808,159 |
| sphinx-doc/sphinx | 2 | 360 | 362 | 0.5% | 7,984 | 2,563 | 21 | 0 | 1,371 | 16 | 0 | 0 | 0 | 15 | 5,299,997 | 4,436,934 |
| sympy/sympy | 5 | 3,069 | 4,033 | 23.9% | 85,656 | 20,879 | 18,105 | 20 | 2,557 | 168 | 0 | 0 | 0 | 132 | 82,004,111 | 73,130,961 |

## Per instance (blob references; hit = cached before this instance was processed)

| instance | blobs | hits | hit rate | on-disk hits | earlier-instance hits | same-repo hit rate | comments removed | docstrings removed | doctest kept | docstrings kept | directives kept | stray kept | unresolved | parse errors | AST failures | `__doc__` files | bytes before | bytes after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astropy__astropy-7336 | 399 | 0 | 0.0% | 0 | 0 | 0.0% | 12,643 | 3,387 | 226 | 91 | 146 | 64 | 0 | 0 | 0 | 45 | 5,589,368 | 3,545,876 |
| astropy__astropy-13398 | 503 | 32 | 6.4% | 0 | 32 | 6.4% | 16,248 | 4,216 | 301 | 116 | 281 | 81 | 0 | 0 | 0 | 61 | 7,244,599 | 4,596,859 |
| astropy__astropy-14365 | 510 | 49 | 9.6% | 0 | 49 | 9.6% | 16,540 | 4,276 | 307 | 115 | 155 | 82 | 0 | 0 | 0 | 61 | 7,412,512 | 4,702,535 |
| astropy__astropy-14598 | 509 | 488 | 95.9% | 0 | 488 | 95.9% | 16,537 | 4,277 | 307 | 115 | 155 | 82 | 0 | 0 | 0 | 61 | 7,415,305 | 4,704,947 |
| django__django-7530 | 843 | 127 | 15.1% | 0 | 127 | 0.0% | 10,394 | 3,513 | 31 | 0 | 256 | 2 | 0 | 0 | 0 | 10 | 4,480,530 | 3,278,522 |
| django__django-14631 | 853 | 170 | 19.9% | 0 | 170 | 19.9% | 10,641 | 3,597 | 31 | 0 | 127 | 0 | 0 | 0 | 0 | 9 | 4,805,091 | 3,601,793 |
| django__django-14787 | 854 | 688 | 80.6% | 0 | 688 | 80.6% | 10,726 | 3,613 | 31 | 0 | 127 | 0 | 0 | 0 | 0 | 9 | 4,846,678 | 3,637,086 |
| matplotlib__matplotlib-14623 | 748 | 4 | 0.5% | 0 | 4 | 0.0% | 17,204 | 4,455 | 46 | 3 | 150 | 27 | 0 | 0 | 0 | 18 | 6,398,509 | 4,007,806 |
| matplotlib__matplotlib-23299 | 770 | 45 | 5.8% | 0 | 45 | 5.8% | 20,187 | 4,442 | 56 | 9 | 154 | 16 | 0 | 0 | 0 | 26 | 6,675,082 | 4,011,091 |
| matplotlib__matplotlib-24970 | 777 | 384 | 49.4% | 0 | 384 | 49.4% | 20,482 | 4,450 | 60 | 9 | 170 | 17 | 0 | 0 | 0 | 27 | 6,763,754 | 4,044,422 |
| matplotlib__matplotlib-25311 | 769 | 187 | 24.3% | 0 | 187 | 24.3% | 19,770 | 4,448 | 60 | 9 | 1,006 | 17 | 0 | 0 | 0 | 27 | 6,722,612 | 4,054,383 |
| mwaskom__seaborn-3069 | 111 | 4 | 3.6% | 0 | 4 | 0.0% | 2,317 | 532 | 1 | 16 | 55 | 0 | 0 | 0 | 0 | 9 | 1,082,079 | 796,077 |
| pallets__flask-5014 | 33 | 0 | 0.0% | 0 | 0 | 0.0% | 657 | 265 | 0 | 0 | 88 | 7 | 0 | 0 | 0 | 2 | 337,291 | 171,067 |
| psf__requests-2931 | 83 | 1 | 1.2% | 0 | 1 | 0.0% | 4,825 | 355 | 19 | 0 | 35 | 0 | 0 | 0 | 0 | 1 | 803,241 | 590,258 |
| pydata__xarray-4356 | 96 | 3 | 3.1% | 0 | 3 | 0.0% | 2,067 | 877 | 91 | 5 | 82 | 1 | 0 | 0 | 0 | 9 | 1,603,853 | 1,144,359 |
| pydata__xarray-7229 | 115 | 10 | 8.7% | 0 | 10 | 8.7% | 2,793 | 1,068 | 233 | 0 | 139 | 0 | 0 | 0 | 0 | 11 | 2,665,580 | 2,081,686 |
| pylint-dev__pylint-6528 | 405 | 0 | 0.0% | 0 | 0 | 0.0% | 3,095 | 1,226 | 7 | 5 | 204 | 67 | 0 | 0 | 0 | 6 | 1,621,352 | 1,282,174 |
| pytest-dev__pytest-5262 | 74 | 2 | 2.7% | 0 | 2 | 0.0% | 1,289 | 634 | 4 | 0 | 40 | 0 | 0 | 0 | 0 | 4 | 777,321 | 576,281 |
| pytest-dev__pytest-10051 | 86 | 5 | 5.8% | 0 | 5 | 5.8% | 1,763 | 815 | 5 | 1 | 153 | 15 | 0 | 0 | 0 | 2 | 1,054,624 | 777,981 |
| scikit-learn__scikit-learn-10297 | 496 | 0 | 0.0% | 0 | 0 | 0.0% | 8,568 | 2,474 | 211 | 5 | 98 | 49 | 0 | 0 | 0 | 214 | 5,472,857 | 3,332,180 |
| scikit-learn__scikit-learn-13142 | 544 | 124 | 22.8% | 0 | 124 | 22.6% | 9,837 | 2,663 | 261 | 0 | 133 | 57 | 0 | 0 | 0 | 218 | 5,945,999 | 3,829,075 |
| scikit-learn__scikit-learn-15100 | 534 | 188 | 35.2% | 0 | 188 | 35.2% | 9,297 | 2,488 | 294 | 0 | 128 | 44 | 0 | 0 | 0 | 230 | 5,994,866 | 3,921,329 |
| scikit-learn__scikit-learn-25102 | 619 | 12 | 1.9% | 0 | 12 | 1.9% | 17,358 | 2,902 | 395 | 0 | 1,194 | 44 | 0 | 0 | 0 | 16 | 8,088,599 | 5,479,853 |
| sphinx-doc__sphinx-8475 | 188 | 1 | 0.5% | 0 | 1 | 0.0% | 3,961 | 1,301 | 11 | 0 | 1,049 | 8 | 0 | 0 | 0 | 7 | 2,811,044 | 2,369,645 |
| sphinx-doc__sphinx-11445 | 174 | 2 | 1.1% | 0 | 2 | 1.1% | 4,023 | 1,262 | 10 | 0 | 322 | 8 | 0 | 0 | 0 | 8 | 2,489,353 | 2,067,689 |
| sympy__sympy-13551 | 675 | 13 | 1.9% | 0 | 13 | 0.0% | 15,186 | 4,090 | 3,371 | 5 | 175 | 33 | 0 | 0 | 0 | 23 | 17,465,490 | 15,851,860 |
| sympy__sympy-16597 | 752 | 180 | 23.9% | 0 | 180 | 23.9% | 17,142 | 4,326 | 3,580 | 4 | 157 | 35 | 0 | 0 | 0 | 27 | 17,085,938 | 15,295,631 |
| sympy__sympy-20916 | 845 | 75 | 8.9% | 0 | 75 | 8.9% | 18,515 | 4,675 | 3,935 | 4 | 751 | 31 | 0 | 0 | 0 | 34 | 18,395,449 | 16,475,215 |
| sympy__sympy-22714 | 883 | 242 | 27.4% | 0 | 242 | 27.4% | 19,699 | 5,024 | 4,175 | 4 | 1,138 | 42 | 0 | 0 | 0 | 36 | 19,348,303 | 17,289,339 |
| sympy__sympy-23824 | 878 | 455 | 51.8% | 0 | 455 | 51.8% | 20,044 | 5,030 | 4,182 | 4 | 638 | 43 | 0 | 0 | 0 | 35 | 19,496,845 | 17,409,970 |

## Docstring context (harness/docuse.py; per-site detail in corpus/pass1-docuse.json)

| instance | consumption sites | tolerant | resolved | unresolved | files w/ kept | docstrings kept (consumed) | files under per-repo rules |
|---|---:|---:|---:|---:|---:|---:|---:|
| astropy__astropy-7336 | 77 | 45 | 13 | 19 | 5 | 10 | 0 |
| astropy__astropy-13398 | 83 | 41 | 8 | 34 | 17 | 31 | 0 |
| astropy__astropy-14365 | 84 | 41 | 8 | 35 | 17 | 31 | 0 |
| astropy__astropy-14598 | 84 | 41 | 8 | 35 | 17 | 31 | 0 |
| django__django-7530 | 8 | 3 | 0 | 5 | 0 | 0 | 0 |
| django__django-14631 | 9 | 4 | 0 | 5 | 0 | 0 | 0 |
| django__django-14787 | 9 | 4 | 0 | 5 | 0 | 0 | 0 |
| matplotlib__matplotlib-14623 | 48 | 31 | 3 | 14 | 3 | 3 | 0 |
| matplotlib__matplotlib-23299 | 38 | 25 | 4 | 9 | 5 | 9 | 0 |
| matplotlib__matplotlib-24970 | 39 | 26 | 4 | 9 | 5 | 9 | 0 |
| matplotlib__matplotlib-25311 | 39 | 26 | 4 | 9 | 5 | 9 | 0 |
| mwaskom__seaborn-3069 | 9 | 5 | 2 | 2 | 6 | 16 | 0 |
| pallets__flask-5014 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| psf__requests-2931 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pydata__xarray-4356 | 7 | 4 | 2 | 1 | 2 | 5 | 0 |
| pydata__xarray-7229 | 197 | 193 | 0 | 4 | 0 | 0 | 0 |
| pylint-dev__pylint-6528 | 6 | 2 | 3 | 1 | 3 | 3 | 1 |
| pytest-dev__pytest-5262 | 6 | 4 | 0 | 2 | 0 | 0 | 0 |
| pytest-dev__pytest-10051 | 5 | 2 | 0 | 3 | 0 | 0 | 0 |
| scikit-learn__scikit-learn-10297 | 212 | 203 | 5 | 4 | 5 | 5 | 0 |
| scikit-learn__scikit-learn-13142 | 218 | 212 | 0 | 6 | 0 | 0 | 0 |
| scikit-learn__scikit-learn-15100 | 228 | 226 | 0 | 2 | 0 | 0 | 0 |
| scikit-learn__scikit-learn-25102 | 16 | 15 | 0 | 1 | 0 | 0 | 0 |
| sphinx-doc__sphinx-8475 | 18 | 7 | 0 | 11 | 0 | 0 | 0 |
| sphinx-doc__sphinx-11445 | 23 | 8 | 0 | 15 | 0 | 0 | 0 |
| sympy__sympy-13551 | 61 | 37 | 9 | 15 | 7 | 9 | 0 |
| sympy__sympy-16597 | 71 | 44 | 10 | 17 | 8 | 10 | 0 |
| sympy__sympy-20916 | 146 | 117 | 12 | 17 | 10 | 12 | 0 |
| sympy__sympy-22714 | 149 | 119 | 12 | 18 | 10 | 12 | 0 |
| sympy__sympy-23824 | 149 | 119 | 12 | 18 | 10 | 12 | 0 |

## Unresolved comments (0 distinct texts; top 20; full list in corpus/pass1-unresolved.tsv)

| count | refs | watch | repos | text | example |
|---:|---:|---|---|---|---|

## AST-check failures / stripper errors (0)

none


## Parse errors (0; left byte-identical, cached as identity)

none
