# Pass 4 report (-sw commits and tags)

Generated 2026-08-24T17:52:04+00:00 · wall 32.7 s (astcheck 14.8 s, artifacts 4.5 s) · jobs 12 · directives sha256 `a333b70274b3` · stripper `dac0bb4d0c8e` · format `sideword/1` · mirror `/Users/esteban/repos/sideword-corpus`

> Run with `--allow-stale-stripper`: the cache was written by stripper `dac0bb4d0c8e`, the running harness is `d46c204100f5`.  Pass 4 re-strips nothing; the `.py` blobs are pass 1's bytes and gate `-nc` proves them equal to the `-nc` tags'.

Instances 30 · gate passed 30 · gate failed 0 · tags created 0 · unchanged 30 · forced 0 · refused 0

Unique blobs re-verified 11,609 (astcheck failures 0) · unique (blob, path) pairs 11,919 · sidedoc blobs 11,609 · index blobs 9,468 · index headers retargeted 310

Commit identity: `sideword <sideword@localhost>` at `2026-08-17T00:00:00Z` (author = committer; deterministic shas).

Gates: **cache** all three cache artifacts present · **AST** stripped == original · **tests** test paths untouched · **tree** base paths + exactly the added `.sideword/` files · **pairs** every `.sideword/` file names a selected path in the tree · **-nc** the two trees are identical outside `.sideword/`.

## Per instance

| instance | base | -sw commit | tag | action | selected | changed | sidedocs | indexes | records | empty docs | sidedoc KiB | index KiB | ~doc tok | cache | AST | unresolved | tests | tree | pairs | -nc | failure |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|---|---|---|
| astropy__astropy-7336 | `732d89c29401` | `d465d3363ea9` | `astropy__astropy-7336-sw` | unchanged | 399 | 387 | 399 | 399 | 10,154 | 12 | 2,422 | 786 | 620,130 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-13398 | `6500928dc0e5` | `7d3a9dac28ab` | `astropy__astropy-13398-sw` | unchanged | 503 | 485 | 503 | 503 | 13,132 | 18 | 3,188 | 1,046 | 815,930 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-14365 | `7269fa3e33e8` | `43fcf435b3b6` | `astropy__astropy-14365-sw` | unchanged | 510 | 490 | 510 | 510 | 13,354 | 20 | 3,256 | 1,064 | 833,380 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-14598 | `80c3854a5f4f` | `dc1e9b0dda45` | `astropy__astropy-14598-sw` | unchanged | 509 | 489 | 509 | 509 | 13,351 | 20 | 3,256 | 1,064 | 833,530 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-7530 | `f8fab6f90233` | `824afd3670f7` | `django__django-7530-sw` | unchanged | 843 | 588 | 843 | 843 | 9,695 | 255 | 1,593 | 774 | 407,690 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-14631 | `84400d2e9db7` | `74f473ea8279` | `django__django-14631-sw` | unchanged | 853 | 606 | 853 | 853 | 9,905 | 247 | 1,619 | 802 | 414,380 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-14787 | `004b4620f6f4` | `65b27444d37b` | `django__django-14787-sw` | unchanged | 854 | 608 | 854 | 854 | 9,974 | 246 | 1,629 | 809 | 417,055 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-14623 | `d65c9ca20ddf` | `9f699be6cb82` | `matplotlib__matplotlib-14623-sw` | unchanged | 748 | 710 | 748 | 748 | 12,282 | 38 | 2,789 | 890 | 714,090 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-23299 | `3eadeacc06c9` | `e57a34fdd05f` | `matplotlib__matplotlib-23299-sw` | unchanged | 770 | 745 | 770 | 770 | 13,205 | 25 | 3,118 | 971 | 798,305 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-24970 | `a3011dfd1aaa` | `852bd10dc9d6` | `matplotlib__matplotlib-24970-sw` | unchanged | 777 | 752 | 777 | 777 | 13,348 | 25 | 3,178 | 981 | 813,270 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-25311 | `430fb1db8884` | `d3636629eb08` | `matplotlib__matplotlib-25311-sw` | unchanged | 769 | 743 | 769 | 769 | 13,330 | 26 | 3,128 | 986 | 800,500 | yes | yes | 0 | yes | yes | yes | yes |  |
| mwaskom__seaborn-3069 | `54cab15bdacf` | `7269d381c514` | `mwaskom__seaborn-3069-sw` | unchanged | 111 | 101 | 111 | 111 | 2,098 | 10 | 384 | 169 | 98,390 | yes | yes | 0 | yes | yes | yes | yes |  |
| pallets__flask-5014 | `7ee9ceb71e86` | `2fa8a72eb9da` | `pallets__flask-5014-sw` | unchanged | 33 | 24 | 33 | 33 | 503 | 9 | 175 | 34 | 45,055 | yes | yes | 0 | yes | yes | yes | yes |  |
| psf__requests-2931 | `5f7a3a74aab1` | `c006348ea0bf` | `psf__requests-2931-sw` | unchanged | 83 | 79 | 83 | 83 | 3,644 | 4 | 340 | 185 | 87,135 | yes | yes | 0 | yes | yes | yes | yes |  |
| pydata__xarray-4356 | `e05fddea852d` | `9a4f3d3c5f91` | `pydata__xarray-4356-sw` | unchanged | 96 | 84 | 96 | 96 | 2,081 | 12 | 531 | 159 | 135,960 | yes | yes | 0 | yes | yes | yes | yes |  |
| pydata__xarray-7229 | `3aa75c8d00a4` | `99293aed9ed5` | `pydata__xarray-7229-sw` | unchanged | 115 | 97 | 115 | 115 | 2,795 | 18 | 688 | 219 | 176,235 | yes | yes | 0 | yes | yes | yes | yes |  |
| pylint-dev__pylint-6528 | `273a8b256204` | `b2588a6be11f` | `pylint-dev__pylint-6528-sw` | unchanged | 405 | 307 | 405 | 405 | 3,093 | 98 | 518 | 294 | 132,750 | yes | yes | 0 | yes | yes | yes | yes |  |
| pytest-dev__pytest-5262 | `58e6a09db49f` | `b54010911e87` | `pytest-dev__pytest-5262-sw` | unchanged | 74 | 66 | 74 | 74 | 1,415 | 8 | 250 | 104 | 64,025 | yes | yes | 0 | yes | yes | yes | yes |  |
| pytest-dev__pytest-10051 | `aa55975c7d3f` | `dd62176bac0d` | `pytest-dev__pytest-10051-sw` | unchanged | 86 | 76 | 86 | 86 | 1,801 | 10 | 336 | 134 | 86,265 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-10297 | `b90661d6a46a` | `0549260f7386` | `scikit-learn__scikit-learn-10297-sw` | unchanged | 496 | 481 | 496 | 496 | 7,793 | 15 | 2,414 | 587 | 618,085 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-13142 | `1c8668b0a021` | `961ff7ebbc31` | `scikit-learn__scikit-learn-13142-sw` | unchanged | 544 | 526 | 544 | 544 | 8,556 | 18 | 2,421 | 646 | 619,785 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-15100 | `af8a6e592a1a` | `c3448f6fec5e` | `scikit-learn__scikit-learn-15100-sw` | unchanged | 534 | 517 | 534 | 534 | 8,025 | 17 | 2,361 | 604 | 604,490 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-25102 | `f9a1cf072da9` | `c0af0252117a` | `scikit-learn__scikit-learn-25102-sw` | unchanged | 619 | 607 | 619 | 619 | 10,089 | 12 | 2,986 | 784 | 764,690 | yes | yes | 0 | yes | yes | yes | yes |  |
| sphinx-doc__sphinx-8475 | `3ea1ec84cc61` | `0e2f97ba688b` | `sphinx-doc__sphinx-8475-sw` | unchanged | 188 | 186 | 188 | 188 | 4,214 | 2 | 642 | 349 | 164,530 | yes | yes | 0 | yes | yes | yes | yes |  |
| sphinx-doc__sphinx-11445 | `71db08c05197` | `6ac86da8d32e` | `sphinx-doc__sphinx-11445-sw` | unchanged | 174 | 172 | 174 | 174 | 4,120 | 2 | 623 | 345 | 159,650 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-13551 | `9476425b9e34` | `5280f539ef73` | `sympy__sympy-13551-sw` | unchanged | 675 | 575 | 675 | 675 | 13,077 | 100 | 2,162 | 1,047 | 553,625 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-16597 | `6fd65310fa31` | `8c4deaf71433` | `sympy__sympy-16597-sw` | unchanged | 752 | 646 | 752 | 752 | 14,641 | 106 | 2,424 | 1,183 | 620,560 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-20916 | `82298df6a514` | `f95c3bbb556f` | `sympy__sympy-20916-sw` | unchanged | 845 | 719 | 845 | 845 | 15,845 | 126 | 2,596 | 1,267 | 664,690 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-22714 | `3ff4717b6aef` | `c7b7380c06c2` | `sympy__sympy-22714-sw` | unchanged | 883 | 755 | 883 | 883 | 16,899 | 128 | 2,770 | 1,344 | 709,200 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-23824 | `39de9a2698ad` | `9f501424cc9f` | `sympy__sympy-23824-sw` | unchanged | 878 | 756 | 878 | 878 | 17,061 | 122 | 2,809 | 1,362 | 719,220 | yes | yes | 0 | yes | yes | yes | yes |  |

## Per repo

| repo | instances | gate passed | failures | created | unchanged | forced | selected | changed | sidedocs | indexes | records | empty docs | sidedoc KiB | index KiB | ~doc tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astropy/astropy | 4 | 4 | 0 | 0 | 4 | 0 | 1,921 | 1,851 | 1,921 | 1,921 | 49,991 | 70 | 12,123 | 3,962 | 3,102,970 |
| django/django | 3 | 3 | 0 | 0 | 3 | 0 | 2,550 | 1,802 | 2,550 | 2,550 | 29,574 | 748 | 4,842 | 2,386 | 1,239,125 |
| matplotlib/matplotlib | 4 | 4 | 0 | 0 | 4 | 0 | 3,064 | 2,950 | 3,064 | 3,064 | 52,165 | 114 | 12,214 | 3,830 | 3,126,165 |
| mwaskom/seaborn | 1 | 1 | 0 | 0 | 1 | 0 | 111 | 101 | 111 | 111 | 2,098 | 10 | 384 | 169 | 98,390 |
| pallets/flask | 1 | 1 | 0 | 0 | 1 | 0 | 33 | 24 | 33 | 33 | 503 | 9 | 175 | 34 | 45,055 |
| psf/requests | 1 | 1 | 0 | 0 | 1 | 0 | 83 | 79 | 83 | 83 | 3,644 | 4 | 340 | 185 | 87,135 |
| pydata/xarray | 2 | 2 | 0 | 0 | 2 | 0 | 211 | 181 | 211 | 211 | 4,876 | 30 | 1,219 | 379 | 312,195 |
| pylint-dev/pylint | 1 | 1 | 0 | 0 | 1 | 0 | 405 | 307 | 405 | 405 | 3,093 | 98 | 518 | 294 | 132,750 |
| pytest-dev/pytest | 2 | 2 | 0 | 0 | 2 | 0 | 160 | 142 | 160 | 160 | 3,216 | 18 | 586 | 238 | 150,290 |
| scikit-learn/scikit-learn | 4 | 4 | 0 | 0 | 4 | 0 | 2,193 | 2,131 | 2,193 | 2,193 | 34,463 | 62 | 10,183 | 2,622 | 2,607,050 |
| sphinx-doc/sphinx | 2 | 2 | 0 | 0 | 2 | 0 | 362 | 358 | 362 | 362 | 8,334 | 4 | 1,266 | 695 | 324,180 |
| sympy/sympy | 5 | 5 | 0 | 0 | 5 | 0 | 4,033 | 3,451 | 4,033 | 4,033 | 77,523 | 582 | 12,763 | 6,206 | 3,267,295 |

## Gate failures

None.


## Worktree sanity checks

| instance | tag | ok | .py | changed .py | .sideword .md | .sideword .idx | comments left | non-directive comments | docstrings left | of which doctests | parse failures | seconds | error |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| pallets__flask-5014 | `pallets__flask-5014-sw` | yes | 80 | 24 | 33 | 33 | 80 | 0 | 0 | 0 | 0 | 0.3 |  |
| sympy__sympy-23824 | `sympy__sympy-23824-sw` | yes | 1,545 | 756 | 878 | 878 | 613 | 0 | 4,078 | 4,078 | 0 | 5.9 |  |

### Sample from `pallets__flask-5014`: `docs/conf.py`

Source 3,005 B, contains `#`: False · sidedoc 489 B

```
sideword/1  docs/conf.py  5 records  ~120 tok
project          lead  1L
master_doc       lead  1L
```
```markdown
---
style: plain
---

## project {lead}
Project --------------------------------------------------------------

## master_doc {lead}
```

### Sample from `sympy__sympy-23824`: `bin/ask_update.py`

Source 2,366 B, contains `#`: True · sidedoc 507 B

```
sideword/1  bin/ask_update.py  4 records  ~130 tok
<module>                     doc   9L
<module>#import:os           lead  1L
```
```markdown
---
style: plain
---

## <module> {doc}
 Update the ``ask_generated.py`` file.

This must be run each time ``known_facts()`` in ``assumptions.facts`` module
```

## Pass 3 (the artifacts these trees carry)

| | |
|---|---|
| blobs | 11,609 |
| errors | 0 |
| gated_code_changed | 0 |
| gated_prose_lost | 0 |
| records | 239,698 |
| unanchorable | 11 |
| unanchorable_rate | 0.0% |
| sidedoc_bytes | 51,899,813 |
| index_bytes | 19,151,391 |
| instances_complete | 30 |

## refs/tags in the mirror

```
astropy__astropy-13398-nc a65d59cfdc36afc18a3a282070e4f7521a1ea7a9 commit
astropy__astropy-13398-sw 7d3a9dac28abe746973f5606b879435fe23d99f6 commit
astropy__astropy-14365-nc cfc07bcff1219bf6d96fc9505b17f03b3546ce8c commit
astropy__astropy-14365-sw 43fcf435b3b6239182b32ea7d5771286d977c1bf commit
astropy__astropy-14598-nc 40f483cb4733e1998b4c8e8c8e660b5a4a17a866 commit
astropy__astropy-14598-sw dc1e9b0dda453a5a659d590339dfa26268b98461 commit
astropy__astropy-7336-nc bfb16b682a1c6ef40046aa8db8cfa07c2f0df7ff commit
astropy__astropy-7336-sw d465d3363ea9e8c4615e2f8148879ba7c35b818f commit
django__django-14631-nc 8477e45ad0b79e174ba50e52667955436eb1b298 commit
django__django-14631-sw 74f473ea82793ef4e35dcb07d4fbfabdf085bafd commit
django__django-14787-nc d3a0d2709bc3bfb14447513f1effed957c025da6 commit
django__django-14787-sw 65b27444d37b4ad913fe37ec0136777b968504b8 commit
django__django-7530-nc 9246bc6a4a4bfcb2f3aa7b68e017da5efa09cfde commit
django__django-7530-sw 824afd3670f7dbf27cea373cf0e09d14b6f9e2a8 commit
matplotlib__matplotlib-14623-nc 5519229de59c8fa6b5f64846653f873ce9222037 commit
matplotlib__matplotlib-14623-sw 9f699be6cb82ad2433e2ef2132a72acfba134689 commit
matplotlib__matplotlib-23299-nc 6a0f769a27cc4bc7bac6e693108b3e4a97bc753e commit
matplotlib__matplotlib-23299-sw e57a34fdd05f27494b7c829a9883869f4eccafa6 commit
matplotlib__matplotlib-24970-nc ac085cfa446f21314216911c8183bb6483eb36c8 commit
matplotlib__matplotlib-24970-sw 852bd10dc9d6ec392ece423484ff4e2556669017 commit
matplotlib__matplotlib-25311-nc e10b7694730ea253e91f400bd9ccdf78aca47412 commit
matplotlib__matplotlib-25311-sw d3636629eb08462f0c9ebfa1e052c5687f5778b7 commit
mwaskom__seaborn-3069-nc de2f28ef10fe4628918c499b47aa0e0219dad66b commit
mwaskom__seaborn-3069-sw 7269d381c5140d0c280458e3e4944b132ae62d1a commit
pallets__flask-5014-nc 0a5aa445a658d7444d0567d54e9a6b8b56743e4c commit
pallets__flask-5014-sw 2fa8a72eb9dad800e3d14c55808a7fb8d0257405 commit
psf__requests-2931-nc 5ab64f6c9966e24e6ee0dd9adf0d9f8fdf7c6614 commit
psf__requests-2931-sw c006348ea0bf617d4dd37210e8e2c7628fbfc909 commit
pydata__xarray-4356-nc cba9d84c1d4e6147da3b18ba3438be10a0697c6d commit
pydata__xarray-4356-sw 9a4f3d3c5f9111c0e8fae74170638890fa04ee5c commit
pydata__xarray-7229-nc ccfd5df3ec25c8b07534f0c8d6dd041d5cfbfc2f commit
pydata__xarray-7229-sw 99293aed9ed57ba0a8953fba1532c19257c0c674 commit
pylint-dev__pylint-6528-nc 0baa20a6d98215c2e37b67c38050921cada411eb commit
pylint-dev__pylint-6528-sw b2588a6be11f18884001a240a235cf9d3c809ed8 commit
pytest-dev__pytest-10051-nc d3c718a3dbca21ffe7594659bc8f5c6226b9d764 commit
pytest-dev__pytest-10051-sw dd62176bac0df02d444bae8e6dfa37c7b3c5128d commit
pytest-dev__pytest-5262-nc f292daa3f72d12250d94a748faf6839edf3a1394 commit
pytest-dev__pytest-5262-sw b54010911e87950e0dfafa59fa9f4d59a5ee0c7c commit
scikit-learn__scikit-learn-10297-nc d0e1262ef777ec6d351339ce2c9310dffd741515 commit
scikit-learn__scikit-learn-10297-sw 0549260f73865e1c6fed3bbd999d2da36d50e19e commit
scikit-learn__scikit-learn-13142-nc be227abfbee7502312d852bddf06e7d9c7626211 commit
scikit-learn__scikit-learn-13142-sw 961ff7ebbc313910697c48bcc3e607e837daa93f commit
scikit-learn__scikit-learn-15100-nc 5531d1d421a152319a821cfc0517b5b1b4f6187f commit
scikit-learn__scikit-learn-15100-sw c3448f6fec5e606fe482a9f460db6aae6f44c301 commit
scikit-learn__scikit-learn-25102-nc 865277bd558d9aa671d8aaa7838c835e9a10251b commit
scikit-learn__scikit-learn-25102-sw c0af0252117a10b66ba03621c86c82916a2c43b3 commit
sphinx-doc__sphinx-11445-nc c0c2a291580cea7989d4133b4ca85f33f252588c commit
sphinx-doc__sphinx-11445-sw 6ac86da8d32e0ce7df10bb751076586bbd5b3f39 commit
sphinx-doc__sphinx-8475-nc 380b6192eb59a448013d4e3418dccf21a89c89f8 commit
sphinx-doc__sphinx-8475-sw 0e2f97ba688b4a446218e58af0f299fecd73f351 commit
sympy__sympy-13551-nc 58c9dc8627a1368bae98b6419120f68b3df998db commit
sympy__sympy-13551-sw 5280f539ef73b4e4e9173e737933acaa0077066d commit
sympy__sympy-16597-nc c4982e1025a73c326ab0c90f12492b381ce4d1e6 commit
sympy__sympy-16597-sw 8c4deaf7143312548e994c4d2bb7012eb5768d1e commit
sympy__sympy-20916-nc c785dfac8112f3e032bbf44a1a4ee751331cd676 commit
sympy__sympy-20916-sw f95c3bbb556fdbb8063b674a1d6c465435277f72 commit
sympy__sympy-22714-nc d7150e437bc79a92ae8f8c856d2877f4ce5f3795 commit
sympy__sympy-22714-sw c7b7380c06c2639c41a62b575a08a6cd2467f42f commit
sympy__sympy-23824-nc 2901d7fa5af97c6005720f6d3a905aebeca3abca commit
sympy__sympy-23824-sw 9f501424cc9f9eb703e708534225e78a8ed5bcd3 commit
```
