# Pass 4 report (-sw commits and tags)

Generated 2026-08-25T02:31:10+00:00 · wall 27.6 s (astcheck 15.7 s, artifacts 4.6 s) · jobs 10 · directives sha256 `f5e1ed55296a` · stripper `6d90ee8b66b2` · format `sideword/1` · mirror `/Users/esteban/repos/sideword-corpus`

Instances 30 · gate passed 30 · gate failed 0 · tags created 0 · unchanged 0 · forced 30 · refused 0

Unique blobs re-verified 11,609 (astcheck failures 0) · unique (blob, path) pairs 11,919 · sidedoc blobs 11,609 · index blobs 9,467 · index headers retargeted 310

Commit identity: `sideword <sideword@localhost>` at `2026-08-17T00:00:00Z` (author = committer; deterministic shas).

Gates: **cache** all three cache artifacts present · **AST** stripped == original · **tests** test paths untouched · **tree** base paths + exactly the added `.sideword/` files · **pairs** every `.sideword/` file names a selected path in the tree · **-nc** the two trees are identical outside `.sideword/`.

## Per instance

| instance | base | -sw commit | tag | action | selected | changed | sidedocs | indexes | records | empty docs | sidedoc KiB | index KiB | ~doc tok | cache | AST | unresolved | tests | tree | pairs | -nc | failure |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|---|---|---|
| astropy__astropy-7336 | `732d89c29401` | `87dc84f9e5b6` | `astropy__astropy-7336-sw` | forced(was d465d3363ea9) | 399 | 387 | 399 | 399 | 10,063 | 12 | 2,402 | 780 | 614,820 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-13398 | `6500928dc0e5` | `c00ed6a3c76a` | `astropy__astropy-13398-sw` | forced(was 7d3a9dac28ab) | 503 | 485 | 503 | 503 | 13,016 | 18 | 3,149 | 1,039 | 806,085 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-14365 | `7269fa3e33e8` | `57aee42f5787` | `astropy__astropy-14365-sw` | forced(was 43fcf435b3b6) | 510 | 490 | 510 | 510 | 13,239 | 20 | 3,218 | 1,056 | 823,670 | yes | yes | 0 | yes | yes | yes | yes |  |
| astropy__astropy-14598 | `80c3854a5f4f` | `2745d7bfbdac` | `astropy__astropy-14598-sw` | forced(was dc1e9b0dda45) | 509 | 489 | 509 | 509 | 13,236 | 20 | 3,218 | 1,057 | 823,820 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-7530 | `f8fab6f90233` | `f898aa01e108` | `django__django-7530-sw` | forced(was 824afd3670f7) | 843 | 588 | 843 | 843 | 9,695 | 255 | 1,593 | 774 | 407,690 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-14631 | `84400d2e9db7` | `ab1a4d08096a` | `django__django-14631-sw` | forced(was 74f473ea8279) | 853 | 606 | 853 | 853 | 9,905 | 247 | 1,619 | 802 | 414,380 | yes | yes | 0 | yes | yes | yes | yes |  |
| django__django-14787 | `004b4620f6f4` | `ef5825db828a` | `django__django-14787-sw` | forced(was 65b27444d37b) | 854 | 608 | 854 | 854 | 9,974 | 246 | 1,629 | 809 | 417,055 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-14623 | `d65c9ca20ddf` | `328cec06a778` | `matplotlib__matplotlib-14623-sw` | forced(was 9f699be6cb82) | 748 | 710 | 748 | 748 | 12,279 | 38 | 2,779 | 890 | 711,680 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-23299 | `3eadeacc06c9` | `32cf8421c0dd` | `matplotlib__matplotlib-23299-sw` | forced(was e57a34fdd05f) | 770 | 744 | 770 | 770 | 13,196 | 26 | 3,106 | 970 | 795,090 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-24970 | `a3011dfd1aaa` | `23e342125151` | `matplotlib__matplotlib-24970-sw` | forced(was 852bd10dc9d6) | 777 | 751 | 777 | 777 | 13,339 | 26 | 3,165 | 980 | 810,055 | yes | yes | 0 | yes | yes | yes | yes |  |
| matplotlib__matplotlib-25311 | `430fb1db8884` | `9bebe472d599` | `matplotlib__matplotlib-25311-sw` | forced(was d3636629eb08) | 769 | 742 | 769 | 769 | 13,321 | 27 | 3,115 | 986 | 797,285 | yes | yes | 0 | yes | yes | yes | yes |  |
| mwaskom__seaborn-3069 | `54cab15bdacf` | `2336a790da5e` | `mwaskom__seaborn-3069-sw` | forced(was 7269d381c514) | 111 | 100 | 111 | 111 | 2,082 | 11 | 378 | 168 | 96,790 | yes | yes | 0 | yes | yes | yes | yes |  |
| pallets__flask-5014 | `7ee9ceb71e86` | `7cd5eeeea8d5` | `pallets__flask-5014-sw` | forced(was 2fa8a72eb9da) | 33 | 24 | 33 | 33 | 503 | 9 | 175 | 34 | 45,055 | yes | yes | 0 | yes | yes | yes | yes |  |
| psf__requests-2931 | `5f7a3a74aab1` | `22e12257065a` | `psf__requests-2931-sw` | forced(was c006348ea0bf) | 83 | 79 | 83 | 83 | 3,644 | 4 | 340 | 185 | 87,135 | yes | yes | 0 | yes | yes | yes | yes |  |
| pydata__xarray-4356 | `e05fddea852d` | `1d893f8b9bec` | `pydata__xarray-4356-sw` | forced(was 9a4f3d3c5f91) | 96 | 84 | 96 | 96 | 2,076 | 12 | 529 | 159 | 135,610 | yes | yes | 0 | yes | yes | yes | yes |  |
| pydata__xarray-7229 | `3aa75c8d00a4` | `c5d4130c55cc` | `pydata__xarray-7229-sw` | forced(was 99293aed9ed5) | 115 | 97 | 115 | 115 | 2,795 | 18 | 688 | 219 | 176,235 | yes | yes | 0 | yes | yes | yes | yes |  |
| pylint-dev__pylint-6528 | `273a8b256204` | `315cb34c32ea` | `pylint-dev__pylint-6528-sw` | forced(was b2588a6be11f) | 405 | 307 | 405 | 405 | 3,088 | 98 | 518 | 294 | 132,610 | yes | yes | 0 | yes | yes | yes | yes |  |
| pytest-dev__pytest-5262 | `58e6a09db49f` | `7c89eded3149` | `pytest-dev__pytest-5262-sw` | forced(was b54010911e87) | 74 | 66 | 74 | 74 | 1,415 | 8 | 250 | 104 | 64,025 | yes | yes | 0 | yes | yes | yes | yes |  |
| pytest-dev__pytest-10051 | `aa55975c7d3f` | `440083925d2a` | `pytest-dev__pytest-10051-sw` | forced(was dd62176bac0d) | 86 | 76 | 86 | 86 | 1,800 | 10 | 336 | 134 | 86,235 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-10297 | `b90661d6a46a` | `c4837a7cd6fd` | `scikit-learn__scikit-learn-10297-sw` | forced(was 0549260f7386) | 496 | 481 | 496 | 496 | 7,788 | 15 | 2,412 | 586 | 617,595 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-13142 | `1c8668b0a021` | `472dec4fd757` | `scikit-learn__scikit-learn-13142-sw` | forced(was 961ff7ebbc31) | 544 | 526 | 544 | 544 | 8,556 | 18 | 2,421 | 646 | 619,785 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-15100 | `af8a6e592a1a` | `d1acca07ad9a` | `scikit-learn__scikit-learn-15100-sw` | forced(was c3448f6fec5e) | 534 | 517 | 534 | 534 | 8,025 | 17 | 2,361 | 604 | 604,490 | yes | yes | 0 | yes | yes | yes | yes |  |
| scikit-learn__scikit-learn-25102 | `f9a1cf072da9` | `18c12157d587` | `scikit-learn__scikit-learn-25102-sw` | forced(was c0af0252117a) | 619 | 607 | 619 | 619 | 10,089 | 12 | 2,986 | 784 | 764,690 | yes | yes | 0 | yes | yes | yes | yes |  |
| sphinx-doc__sphinx-8475 | `3ea1ec84cc61` | `e0e7d70ef6c7` | `sphinx-doc__sphinx-8475-sw` | forced(was 0e2f97ba688b) | 188 | 186 | 188 | 188 | 4,214 | 2 | 642 | 349 | 164,530 | yes | yes | 0 | yes | yes | yes | yes |  |
| sphinx-doc__sphinx-11445 | `71db08c05197` | `9ee39eccec68` | `sphinx-doc__sphinx-11445-sw` | forced(was 6ac86da8d32e) | 174 | 172 | 174 | 174 | 4,120 | 2 | 623 | 345 | 159,650 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-13551 | `9476425b9e34` | `5f4afc2773fb` | `sympy__sympy-13551-sw` | forced(was 5280f539ef73) | 675 | 575 | 675 | 675 | 13,072 | 100 | 2,161 | 1,047 | 553,205 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-16597 | `6fd65310fa31` | `25b1abf3a7d2` | `sympy__sympy-16597-sw` | forced(was 8c4deaf71433) | 752 | 646 | 752 | 752 | 14,637 | 106 | 2,423 | 1,183 | 620,410 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-20916 | `82298df6a514` | `1393e2694667` | `sympy__sympy-20916-sw` | forced(was f95c3bbb556f) | 845 | 719 | 845 | 845 | 15,841 | 126 | 2,595 | 1,267 | 664,530 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-22714 | `3ff4717b6aef` | `8be627138ea3` | `sympy__sympy-22714-sw` | forced(was c7b7380c06c2) | 883 | 755 | 883 | 883 | 16,895 | 128 | 2,769 | 1,344 | 709,040 | yes | yes | 0 | yes | yes | yes | yes |  |
| sympy__sympy-23824 | `39de9a2698ad` | `d79d269eab8c` | `sympy__sympy-23824-sw` | forced(was 9f501424cc9f) | 878 | 756 | 878 | 878 | 17,057 | 122 | 2,808 | 1,362 | 719,050 | yes | yes | 0 | yes | yes | yes | yes |  |

## Per repo

| repo | instances | gate passed | failures | created | unchanged | forced | selected | changed | sidedocs | indexes | records | empty docs | sidedoc KiB | index KiB | ~doc tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astropy/astropy | 4 | 4 | 0 | 0 | 0 | 4 | 1,921 | 1,851 | 1,921 | 1,921 | 49,554 | 70 | 11,988 | 3,933 | 3,068,395 |
| django/django | 3 | 3 | 0 | 0 | 0 | 3 | 2,550 | 1,802 | 2,550 | 2,550 | 29,574 | 748 | 4,842 | 2,386 | 1,239,125 |
| matplotlib/matplotlib | 4 | 4 | 0 | 0 | 0 | 4 | 3,064 | 2,947 | 3,064 | 3,064 | 52,135 | 117 | 12,167 | 3,828 | 3,114,110 |
| mwaskom/seaborn | 1 | 1 | 0 | 0 | 0 | 1 | 111 | 100 | 111 | 111 | 2,082 | 11 | 378 | 168 | 96,790 |
| pallets/flask | 1 | 1 | 0 | 0 | 0 | 1 | 33 | 24 | 33 | 33 | 503 | 9 | 175 | 34 | 45,055 |
| psf/requests | 1 | 1 | 0 | 0 | 0 | 1 | 83 | 79 | 83 | 83 | 3,644 | 4 | 340 | 185 | 87,135 |
| pydata/xarray | 2 | 2 | 0 | 0 | 0 | 2 | 211 | 181 | 211 | 211 | 4,871 | 30 | 1,218 | 378 | 311,845 |
| pylint-dev/pylint | 1 | 1 | 0 | 0 | 0 | 1 | 405 | 307 | 405 | 405 | 3,088 | 98 | 518 | 294 | 132,610 |
| pytest-dev/pytest | 2 | 2 | 0 | 0 | 0 | 2 | 160 | 142 | 160 | 160 | 3,215 | 18 | 586 | 238 | 150,260 |
| scikit-learn/scikit-learn | 4 | 4 | 0 | 0 | 0 | 4 | 2,193 | 2,131 | 2,193 | 2,193 | 34,458 | 62 | 10,181 | 2,621 | 2,606,560 |
| sphinx-doc/sphinx | 2 | 2 | 0 | 0 | 0 | 2 | 362 | 358 | 362 | 362 | 8,334 | 4 | 1,266 | 695 | 324,180 |
| sympy/sympy | 5 | 5 | 0 | 0 | 0 | 5 | 4,033 | 3,451 | 4,033 | 4,033 | 77,502 | 582 | 12,759 | 6,205 | 3,266,235 |

## Gate failures

None.


## Pass 3 (the artifacts these trees carry)

| | |
|---|---|
| blobs | 11,609 |
| errors | 0 |
| gated_code_changed | 0 |
| gated_prose_lost | 0 |
| records | 239,306 |
| unanchorable | 11 |
| unanchorable_rate | 0.0% |
| sidedoc_bytes | 51,743,516 |
| index_bytes | 19,125,252 |
| instances_complete | 30 |

## refs/tags in the mirror

```
astropy__astropy-13398-nc ba7dfefc85db8bfdf4e274edd361dba6f07a412b commit
astropy__astropy-13398-sw c00ed6a3c76a66628da007f7e0008a42f2e20224 commit
astropy__astropy-14365-nc 3d3ffc42f5843f6c77033104c7a8b5478a1b6d60 commit
astropy__astropy-14365-sw 57aee42f5787235a805dfad2a26bda4ccc54d724 commit
astropy__astropy-14598-nc d2ed9152f684a4c910d29f0c94e400ba06878b78 commit
astropy__astropy-14598-sw 2745d7bfbdac63b60deaa57666c4ee2f0a0922b3 commit
astropy__astropy-7336-nc 464f5c527e0f22aad6a7ad6a286b52149bcff230 commit
astropy__astropy-7336-sw 87dc84f9e5b624bc6353fd055a60d8c8eccbf4a3 commit
django__django-14631-nc f76d41107b9c7224a719d1c618a5d34be0cd64d8 commit
django__django-14631-sw ab1a4d08096a4b636b268d9df15848aed003259e commit
django__django-14787-nc 6a2908f2dcf06a7917bf3d26751552538efebbff commit
django__django-14787-sw ef5825db828ab01ce3499cea7135b7f122e1b196 commit
django__django-7530-nc 83be52822749cb5ffd298eed568969b62cfa085e commit
django__django-7530-sw f898aa01e108d6b3565aed8f1443d8ba643bb585 commit
matplotlib__matplotlib-14623-nc 14271ae7b4e1717b1ad0178d1b15da249f631551 commit
matplotlib__matplotlib-14623-sw 328cec06a7781c1a1b82209453486ace998e876a commit
matplotlib__matplotlib-23299-nc 9af7636d3acbfe59b36749695d9eee20366fd88d commit
matplotlib__matplotlib-23299-sw 32cf8421c0dd6dfdcaf4ba00261f398c5d7855bf commit
matplotlib__matplotlib-24970-nc 859f1f085afcd7471d195393a5e50a567a496a20 commit
matplotlib__matplotlib-24970-sw 23e342125151d37f3c0d02221fc98de9756904f7 commit
matplotlib__matplotlib-25311-nc 8dd7a3dc178995b53491b77bfd02c4ba06b34e91 commit
matplotlib__matplotlib-25311-sw 9bebe472d59969a18f849986363a48f523e7554e commit
mwaskom__seaborn-3069-nc 9eaae29fa3a12f045893cbefd0a1850dbd4e367a commit
mwaskom__seaborn-3069-sw 2336a790da5e130ee212849efc76519ed684dd82 commit
pallets__flask-5014-nc e4ac66178db34e2a7a0421572e8741af9b4796db commit
pallets__flask-5014-sw 7cd5eeeea8d551d4a3fd46123c477a37960b3e53 commit
psf__requests-2931-nc 8fa1111f55bcf53402f29ed0f698651f4e9abbd2 commit
psf__requests-2931-sw 22e12257065a3dcd48015fa199b9c775397da156 commit
pydata__xarray-4356-nc 94354dd8140eb491873d750c427390beda8ba7a1 commit
pydata__xarray-4356-sw 1d893f8b9bec5e890a815717d19c0cb224f19c62 commit
pydata__xarray-7229-nc 49df3f65762e0c53271338ad3f7a70b54a284ffe commit
pydata__xarray-7229-sw c5d4130c55cc6fbd9b890888fc99a725b29c5c43 commit
pylint-dev__pylint-6528-nc c2c44b6b95ca0da5a594aa20ef412a3c0ea1ec40 commit
pylint-dev__pylint-6528-sw 315cb34c32ea27911228439cb09eadf169693d4f commit
pytest-dev__pytest-10051-nc 9b33bde8a2dcbf065ccd8f3b16d561029fa81f6d commit
pytest-dev__pytest-10051-sw 440083925d2a901538ad032c5e50cf180325a116 commit
pytest-dev__pytest-5262-nc a579c75521c99e06d3e28a9735da5c95b7f1d969 commit
pytest-dev__pytest-5262-sw 7c89eded3149254778c2ed9e61d2c614700b1420 commit
scikit-learn__scikit-learn-10297-nc bad39de935badc3b013965182932c7ca2656d74a commit
scikit-learn__scikit-learn-10297-sw c4837a7cd6fdc4892efbcd12d1a69db0f857de29 commit
scikit-learn__scikit-learn-13142-nc 73b2fa9498ee2adb38837c25ea6656e06351058b commit
scikit-learn__scikit-learn-13142-sw 472dec4fd7570209054cbd22836682408b0de88f commit
scikit-learn__scikit-learn-15100-nc bf1f9a85415b282d3739dc389ddb2e95768296aa commit
scikit-learn__scikit-learn-15100-sw d1acca07ad9a5fb06d16fb8e6bfa628c7b79062e commit
scikit-learn__scikit-learn-25102-nc 4320fe51a5c747000bf1e317a698557aae31df9f commit
scikit-learn__scikit-learn-25102-sw 18c12157d58770f86d9c024ec367d6acc3490232 commit
sphinx-doc__sphinx-11445-nc 6bef04026a1b9eafc4640a2e8935e66915386fdc commit
sphinx-doc__sphinx-11445-sw 9ee39eccec68e8ecd84a85e6e8746580bdbbd1b9 commit
sphinx-doc__sphinx-8475-nc 4ee93accfa25ce30458d3399902275fcac987d94 commit
sphinx-doc__sphinx-8475-sw e0e7d70ef6c78ddbfc0d97c845413e6aca095b86 commit
sympy__sympy-13551-nc 865ba3bdec07119e69ee504d61744a94d0eef8cb commit
sympy__sympy-13551-sw 5f4afc2773fb6ad234b43e669c26df4c18c264b2 commit
sympy__sympy-16597-nc 33a6c4b134500613eb30bec226904f5b7b6ecbd3 commit
sympy__sympy-16597-sw 25b1abf3a7d2df6e8bc05346487ff59b1ccd4840 commit
sympy__sympy-20916-nc f1f5b16ccca7076b2be93ec35c34496beb600b2c commit
sympy__sympy-20916-sw 1393e269466701e762f76a9fc5c7f068dfacee74 commit
sympy__sympy-22714-nc 0aa27c40f0b86761e41ddca98dbf330e7bcebb46 commit
sympy__sympy-22714-sw 8be627138ea3a953943ce8857eba43dd0e92b6b3 commit
sympy__sympy-23824-nc 7fc1194d6184e380a7d6098c7dddaff754045f5c commit
sympy__sympy-23824-sw d79d269eab8c170b3f76159afdddf122c695ef97 commit
```
