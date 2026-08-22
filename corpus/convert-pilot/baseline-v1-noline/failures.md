# Converter pilot — failure log (EST-81 deliverable)

Every record the model called unanchorable, every anchor the resolver rejected (malformed / missing / ambiguous), and every anchor that resolved to the wrong place. All three efforts pooled; each item is tagged with its effort. Grouped by pattern, most frequent first. `expected` = line(s) the record should attach to; `resolved` = line the resolver put the anchor on.


## unanchorable (1)


### inside a multi-line expression (condition / call args) (1)

- [medium] `pylint/checkers/variables.py` (cc103e894a) r145 comment line 1952 expected [1955] — reason: 'Comment sits inside a boolean sub-expression of an elif condition (lines 1938-1969); no statement or element kind names a fragment of an expression.'; resolver has anchors at expected line: False

## malformed (0)


## missing (65)


### segment `assign` names nothing under a resolved prefix (residual) (22)

- [medium] `astropy/modeling/tabular.py` (bd80ececa9) r9 comment line 274 expected [275] `_Tabular.inverse#if:self.n_inputs == 1/elif:np.all(np.diff(self.lookup_table) < 0)/assign:points` — resolved prefix: _Tabular.inverse#if:self.n_inputs == 1; suggestions: ['_Tabular.inverse#if:self.n_inputs==1/if:np.all(np.diff(self.lookup_table)>0)/assign:points', '_Tabular.inverse#if:self.n_inputs==1/if:np.all(np.diff(self.lookup_table)>0)/elif/assign:points', '_Tabular.inverse#if:self.n_inputs==1/if:np.all(np.diff(self.lookup_table)>0)/assign:lookup_table']
- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r31 comment line 412 expected [412] `_strip_comment#while:True/if:quote_pos<0/elif:0<=hash_pos<quote_pos/else/assign:pos` — resolved prefix: _strip_comment#while:True/if:quote_pos<0/elif:0<=hash_pos<quote_pos; suggestions: ['_strip_comment#while:True/if:quote_pos<0/elif:0<=hash_pos<quote_pos/return', '_strip_comment#while:True/if:quote_pos<0/elif:0<=hash_pos<quote_pos']
- [medium] `django/db/models/sql/compiler.py` (eda7fc3b5e) r80 comment line 1282 expected [1284] `SQLInsertCompiler.field_as_sql#if:field is None/elif:hasattr(val, 'as_sql')/elif:hasattr(field, 'get_placeholder')/assign:sql, params` — resolved prefix: SQLInsertCompiler.field_as_sql#if:field is None/elif:hasattr(val, 'as_sql'); suggestions: ["SQLInsertCompiler.field_as_sql#if:fieldisNone/elif:hasattr(field,'get_placeholder')/assign:sql,params"]
- [medium] `django/db/models/sql/compiler.py` (eda7fc3b5e) r81 comment line 1286 expected [1287] `SQLInsertCompiler.field_as_sql#if:field is None/elif:hasattr(val, 'as_sql')/elif:hasattr(field, 'get_placeholder')/else/assign:sql, params` — resolved prefix: SQLInsertCompiler.field_as_sql#if:field is None/elif:hasattr(val, 'as_sql'); suggestions: ["SQLInsertCompiler.field_as_sql#if:fieldisNone/elif:hasattr(field,'get_placeholder')/assign:sql,params"]
- [medium] `sphinx/ext/autosummary/__init__.py` (76d99b83e8) r55 comment line 545 expected [546] `extract_summary#if:isinstance(node[0], nodes.section)/elif:not isinstance(node[0], nodes.paragraph)/else/assign:sentences` — resolved prefix: extract_summary#if:isinstance(node[0], nodes.section)/elif:not isinstance(node[0], nodes.paragraph); suggestions: ['extract_summary#if:isinstance(node[0],nodes.section)/elif:notisinstance(node[0],nodes.paragraph)/assign:summary', 'extract_summary#if:isinstance(node[0],nodes.section)/elif:notisinstance(node[0],nodes.paragraph)']
- [medium] `sphinx/domains/python.py` (3fda527035) r28 comment line 530 expected [532] `PyObject.handle_signature#if:classname/elif:prefix/assign:fullname` — resolved prefix: PyObject.handle_signature#if:classname; suggestions: ['PyObject.handle_signature#if:classname/else/if:prefix/assign:fullname', 'PyObject.handle_signature#if:classname/else/if:prefix/assign:classname', 'PyObject.handle_signature#if:classname/else/if:prefix/else/assign:fullname']
- [medium] `sphinx/domains/python.py` (3fda527035) r29 comment line 534 expected [535] `PyObject.handle_signature#if:classname/else/assign:fullname` — resolved prefix: PyObject.handle_signature#if:classname/else; suggestions: ['PyObject.handle_signature#if:classname/else/assign:add_module', 'PyObject.handle_signature#if:classname/else/if:prefix/assign:fullname', 'PyObject.handle_signature#if:classname/else/if:prefix']
- [medium] `pylint/utils/utils.py` (f56fc8eb22) r18 comment line 348 expected [349] `_format_option_value#if:optdict.get("type", None) == "py_version"/elif:isinstance(value, (list, tuple))/elif:isinstance(value, dict)/elif:hasattr(value, "match")/assign:value` — resolved prefix: _format_option_value#if:optdict.get("type", None) == "py_version"/elif:isinstance(value, (list, tuple)); suggestions: []
- [medium] `seaborn/_oldcore.py` (192af381bf) r21 comment line 155 expected [156] `HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/else/assign:cmap` — resolved prefix: HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:cmap', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table']
- [medium] `seaborn/_oldcore.py` (192af381bf) r48 comment line 410 expected [421] `SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list)/else/if:isinstance(sizes, tuple)/elif:sizes is not None/else/assign:sizes` — resolved prefix: SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list); suggestions: ['SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/else/if:isinstance(sizes,tuple)/elif:sizesisnotNone/assign:err']
- [medium] `seaborn/_oldcore.py` (192af381bf) r49 comment line 413 expected [421] `SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list)/else/if:isinstance(sizes, tuple)/elif:sizes is not None/else/assign:sizes` — resolved prefix: SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list); suggestions: ['SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/else/if:isinstance(sizes,tuple)/elif:sizesisnotNone/assign:err']
- [medium] `seaborn/_oldcore.py` (192af381bf) r50 comment line 423 expected [428] `SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list)/else/assign:sizes` — resolved prefix: SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list); suggestions: ['SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/elif:isinstance(sizes,list)/assign:sizes', 'SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/else/if:isinstance(sizes,tuple)/else/assign:sizes', 'SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/elif:isinstance(sizes,list)/assign:sizes/arg:sizes']
- [medium] `seaborn/_oldcore.py` (192af381bf) r54 comment line 468 expected [471] `SizeMapping.numeric_mapping#if:isinstance(sizes, dict)/else/if:isinstance(sizes, tuple)/elif:sizes is not None/else/assign:size_range` — resolved prefix: SizeMapping.numeric_mapping; suggestions: ['SizeMapping.numeric_mapping#if:isinstance(sizes,dict)~1/else/if:isinstance(sizes,tuple)/elif:sizesisnotNone/assign:err', 'SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/else/if:isinstance(sizes,tuple)/elif:sizesisnotNone/assign:err', 'SizeMapping.numeric_mapping#if:isinstance(sizes,dict)~1/else/if:isinstance(sizes,tuple)/elif:sizesisnotNone/raise:ValueError']
- [medium] `seaborn/_oldcore.py` (192af381bf) r58 comment line 489 expected [490] `SizeMapping.numeric_mapping#if:norm is None/elif:isinstance(norm, tuple)/elif:not isinstance(norm, mpl.colors.Normalize)/else/assign:norm` — resolved prefix: SizeMapping.numeric_mapping#if:norm is None/elif:isinstance(norm, tuple); suggestions: []
- [medium] `seaborn/_oldcore.py` (192af381bf) r93 comment line 799 expected [801] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/if:isinstance(data, Sequence)/for:i, var in enumerate(data)/assign:data_dict[key]` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)/for:i,varinenumerate(data)/assign:data_dict[key]', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)/for:i,varinenumerate(data)/assign:data_dict[key]/arg:var', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)/for:i,varinenumerate(data)/assign:key']
- [medium] `seaborn/_oldcore.py` (192af381bf) r95 comment line 810 expected [814] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/assign:wide_data` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:flat_data', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:plot_data~1', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:plot_data~2']
- [medium] `seaborn/_oldcore.py` (192af381bf) r96 comment line 816 expected [817] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/assign:numeric_cols` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/assign:numeric_cols', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:names', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:variables']
- [medium] `seaborn/_oldcore.py` (192af381bf) r97 comment line 822 expected [823] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/assign:melt_kws` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/assign:melt_kws', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:flat_data', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:names']
- [medium] `seaborn/_oldcore.py` (192af381bf) r99 comment line 848 expected [849] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/assign:variables` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:variables', 'VectorPlotter._assign_variables_wideform#if:empty/elif/assign:variables', 'VectorPlotter._assign_variables_wideform#if:empty/else/assign:variables']
- [medium] `seaborn/_oldcore.py` (192af381bf) r100 comment line 854 expected [855] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/assign:plot_data` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:flat_data', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:plot_data~1', 'VectorPlotter._assign_variables_wideform#if:empty/elif:flat/assign:plot_data~2']
- [medium] `seaborn/_oldcore.py` (192af381bf) r111 comment line 957 expected [958] `VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes))/else/assign:variables[key]` — resolved prefix: VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes)); suggestions: ['VectorPlotter._assign_variables_longform#for:key,valinkwargs.items()/if:val_as_data_key/elif:isinstance(val,(str,bytes))/assign:err', 'VectorPlotter._assign_variables_longform#for:key,valinkwargs.items()/if:val_as_data_key/elif:isinstance(val,(str,bytes))/raise:ValueError', 'VectorPlotter._assign_variables_longform#for:key,valinkwargs.items()/if:val_as_data_key/elif:isinstance(val,(str,bytes))']
- [medium] `src/flask/testing.py` (8cb2d1bd94) r6 comment line 211 expected [212] `FlaskClient.open#if:args and isinstance(args[0], (werkzeug.test.EnvironBuilder, dict, BaseRequest))/if:isinstance(args[0], werkzeug.test.EnvironBuilder)/elif:isinstance(args[0], dict)/else/assign:request` — resolved prefix: FlaskClient.open#if:args and isinstance(args[0], (werkzeug.test.EnvironBuilder, dict, BaseRequest))/if:isinstance(args[0], werkzeug.test.EnvironBuilder)/elif:isinstance(args[0], dict); suggestions: ['FlaskClient.open#if:argsandisinstance(args[0],(werkzeug.test.EnvironBuilder,dict,BaseRequest))/if:isinstance(args[0],werkzeug.test.EnvironBuilder)/elif:isinstance(args[0],dict)/assign:request', 'FlaskClient.open#if:argsandisinstance(args[0],(werkzeug.test.EnvironBuilder,dict,BaseRequest))/if:isinstance(args[0],werkzeug.test.EnvironBuilder)/elif:isinstance(args[0],dict)', 'FlaskClient.open#if:argsandisinstance(args[0],(werkzeug.test.EnvironBuilder,dict,BaseRequest))/if:isinstance(args[0],werkzeug.test.EnvironBuilder)/elif/assign:request']

### segment `return` names nothing under a resolved prefix (residual) (8)

- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r111 comment line 1320 expected [1321] `_reshape_2D#if:isinstance(X, np.ndarray)/elif:X.ndim==1 and np.ndim(X[0])==0/return` — resolved prefix: _reshape_2D#if:isinstance(X, np.ndarray); suggestions: ['_reshape_2D#if:isinstance(X,np.ndarray)/if:len(X)==0/elif:X.ndim==1andnp.ndim(X[0])==0/return', '_reshape_2D#if:isinstance(X,np.ndarray)/if:len(X)==0/elif:X.ndim==1andnp.ndim(X[0])==0', '_reshape_2D#if:isinstance(X,np.ndarray)/if:len(X)==0/elif:X.ndim==1andnp.ndim(X[0])==0/return/item:X']
- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r112 comment line 1323 expected [1324] `_reshape_2D#if:isinstance(X, np.ndarray)/elif:X.ndim==1 and np.ndim(X[0])==0/elif:X.ndim in [1, 2]/return` — resolved prefix: _reshape_2D#if:isinstance(X, np.ndarray); suggestions: ['_reshape_2D#if:isinstance(X,np.ndarray)/if:len(X)==0/elif:X.ndimin[1,2]/return']
- [medium] `django/db/models/fields/__init__.py` (84c81f9e21) r33 comment line 534 expected [534] `Field.__lt__#if:isinstance(other, Field)/elif:hasattr(self, 'model') != hasattr(other, 'model')/return` — resolved prefix: Field.__lt__#if:isinstance(other, Field); suggestions: []
- [medium] `django/db/models/fields/__init__.py` (84c81f9e21) r34 comment line 536 expected [537] `Field.__lt__#if:isinstance(other, Field)/elif:hasattr(self, 'model') != hasattr(other, 'model')/else/return` — resolved prefix: Field.__lt__#if:isinstance(other, Field); suggestions: []
- [medium] `django/db/models/fields/__init__.py` (84c81f9e21) r78 comment line 1176 expected [1177] `DateField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.date)/else/return` — resolved prefix: DateField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.date); suggestions: ['DateField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)/pass', 'DateField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)', 'DateTimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)/assign:value']
- [medium] `django/db/models/fields/__init__.py` (84c81f9e21) r83 comment line 1322 expected [1323] `DateTimeField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.date)/else/return` — resolved prefix: DateTimeField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.date); suggestions: ['DateTimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)/assign:value', 'DateTimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)', 'DateTimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.date)/assign:lower~1']
- [medium] `django/db/models/fields/__init__.py` (84c81f9e21) r96 comment line 2218 expected [2219] `TimeField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.time)/else/return` — resolved prefix: TimeField._check_fix_default_value#if:isinstance(value, datetime.datetime)/elif:isinstance(value, datetime.time); suggestions: ['TimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.time)/assign:lower', 'TimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.time)/assign:upper', 'TimeField._check_fix_default_value#if:isinstance(value,datetime.datetime)/elif:isinstance(value,datetime.time)/assign:value']
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r32 comment line 396 expected [397] `StandaloneHTMLBuilder.math_renderer_name#if:name is not None/else/if:len(renderers)==1/elif:len(renderers)==2/else/return` — resolved prefix: StandaloneHTMLBuilder.math_renderer_name#if:name is not None/else/if:len(renderers)==1/elif:len(renderers)==2; suggestions: ['StandaloneHTMLBuilder.math_renderer_name#if:nameisnotNone/else/if:len(renderers)==1/elif:len(renderers)==2/return', 'StandaloneHTMLBuilder.math_renderer_name#if:nameisnotNone/else/if:len(renderers)==1/elif:len(renderers)==2', 'StandaloneHTMLBuilder.math_renderer_name#if:nameisnotNone/else/if:len(renderers)==1/elif:len(renderers)==2/call:renderers.remove']

### segment `if` names nothing under a resolved prefix (residual) (7)

- [medium] `astropy/io/fits/fitsrec.py` (f82a0ee516) r12 comment line 202 expected [204] `FITS_rec.__reduce__#for:attrs in ['_converted', '_heapoffset', '_heapsize', '_nfields', '_gap', '_uint',/with:suppress(AttributeError)/if:attrs == '_coldefs'` — resolved prefix: FITS_rec.__reduce__; suggestions: ["FITS_rec.__reduce__#for:attrsin['_converted','_heapoffset','_heapsize','_nfields','_gap','_uint','parnam/with:suppress(AttributeError)/if:attrs=='_coldefs'", "FITS_rec.__reduce__#for:attrsin['_converted','_heapoffset','_heapsize','_nfields','_gap','_uint','parnam/with:suppress(AttributeError)/if:attrs=='_coldefs'/else", "FITS_rec.__reduce__#for:attrsin['_converted','_heapoffset','_heapsize','_nfields','_gap','_uint','parnam/with:suppress(AttributeError)/call:meta.append"]
- [medium] `seaborn/_oldcore.py` (192af381bf) r47 comment line 398 expected [399] `SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list)/else/if:isinstance(sizes, tuple)/if:len(sizes)!=2` — resolved prefix: SizeMapping.categorical_mapping#if:isinstance(sizes, dict)/elif:isinstance(sizes, list); suggestions: ['SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/else/if:isinstance(sizes,tuple)/if:len(sizes)!=2', 'SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/elif:isinstance(sizes,list)/assign:sizes/arg:"sizes"', 'SizeMapping.categorical_mapping#if:isinstance(sizes,dict)/elif:isinstance(sizes,list)/assign:sizes/arg:sizes']
- [medium] `seaborn/_oldcore.py` (192af381bf) r91 comment line 790 expected [795] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/if:isinstance(data, Sequence)` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Mapping)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)/assign:data']
- [medium] `seaborn/_oldcore.py` (192af381bf) r92 comment line 792 expected [795] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/if:isinstance(data, Sequence)` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Mapping)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)/assign:data']
- [medium] `seaborn/_oldcore.py` (192af381bf) r94 comment line 805 expected [807] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/if:isinstance(data, Mapping)` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Mapping)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Sequence)', 'VectorPlotter._assign_variables_wideform#if:empty/else/if:isinstance(data,Mapping)/assign:data']
- [medium] `seaborn/_oldcore.py` (192af381bf) r109 comment line 942 expected [945] `VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes))/else/if:isinstance(data, pd.DataFrame) and not isinstance(val, pd.Series)` — resolved prefix: VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes)); suggestions: ['VectorPlotter._assign_variables_longform#for:key,valinkwargs.items()/if:val_as_data_key/else/if:isinstance(data,pd.DataFrame)andnotisinstance(val,pd.Series)']
- [medium] `seaborn/_oldcore.py` (192af381bf) r110 comment line 944 expected [945] `VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes))/else/if:isinstance(data, pd.DataFrame) and not isinstance(val, pd.Series)` — resolved prefix: VectorPlotter._assign_variables_longform#for:key, val in kwargs.items()/if:val_as_data_key/elif:isinstance(val, (str, bytes)); suggestions: ['VectorPlotter._assign_variables_longform#for:key,valinkwargs.items()/if:val_as_data_key/else/if:isinstance(data,pd.DataFrame)andnotisinstance(val,pd.Series)']

### segment `arg` names nothing under a resolved prefix (residual) (7)

- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r23 comment line 345 expected [346] `<module>#assign:an1/arg:ha` — resolved prefix: <module>#assign:an1; suggestions: ['<module>#assign:ann~3/arg:va', '<module>#assign:ann~2/arg:xy', '<module>#assign:ann~3/arg:xy']
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r24 comment line 348 expected [349] `<module>#assign:an1/arg:bbox` — resolved prefix: <module>#assign:an1; suggestions: ['<module>#assign:ann~2/arg:bbox', '<module>#assign:ann~3/arg:bbox', '<module>#assign:ann~2/arg:size']
- [medium] `pylint/utils/utils.py` (f56fc8eb22) r23 comment line 410 expected [414] `IsortDriver.__init__#if:HAS_ISORT_5/assign:self.isort5_config/arg:extra_standard_library` — resolved prefix: IsortDriver.__init__#if:HAS_ISORT_5/assign:self.isort5_config; suggestions: []
- [medium] `xarray/core/accessor_str.py` (2c74d2bed1) r73 comment line 1912 expected [1914] `StringAccessor.extractall#return/arg:func` — resolved prefix: StringAccessor.extractall#return; suggestions: ['StringAccessor.findall#return/arg:func', 'StringAccessor.istitle#return/arg:func', 'StringAccessor.title#return/arg:func']
- [medium] `seaborn/relational.py` (fa8b3583b3) r1 comment line 27 expected [28] `_relational_narrative#arg:main_api` — resolved prefix: _relational_narrative; suggestions: []
- [medium] `seaborn/_oldcore.py` (192af381bf) r22 comment line 158 expected [160] `HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/else/assign:levels, lookup_table/arg:list(data)` — resolved prefix: HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:data', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:order', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:palette']
- [medium] `seaborn/_oldcore.py` (192af381bf) r44 comment line 340 expected [342] `SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/else/assign:levels, lookup_table/arg:list(data)` — resolved prefix: SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:data', 'SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:order', 'SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/assign:levels,lookup_table/arg:sizes']

### segment `item` names nothing under a resolved prefix (residual) (5)

- [medium] `examples/compose/plot_compare_reduction.py` (ee87033355) r4 comment line 45 expected [46] `pipe#arg:[('reduce_dim', 'passthrough'), ('classify', LinearSVC(dual=False, max_iter=1000/item:('reduce_dim', 'passthrough')` — resolved prefix: pipe; suggestions: ["pipe#arg:[('reduce_dim','passthrough'),('classify',LinearSVC(dual=False,max_iter=10000))]/item:'reduce_dim','passthrough'", "pipe#arg:[('reduce_dim','passthrough'),('classify',LinearSVC(dual=False,max_iter=10000))]/item:'reduce_dim','passthrough'/item:'reduce_dim'", "pipe#arg:[('reduce_dim','passthrough'),('classify',LinearSVC(dual=False,max_iter=10000))]/item:'reduce_dim','passthrough'/item:'passthrough'"]
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r3 comment line 59 expected [60] `DOMAIN_INDEX_TYPE#item:str` — resolved prefix: DOMAIN_INDEX_TYPE; suggestions: []
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r4 comment line 61 expected [62] `DOMAIN_INDEX_TYPE#item:Type[Index]` — resolved prefix: DOMAIN_INDEX_TYPE; suggestions: []
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r5 comment line 63 expected [64] `DOMAIN_INDEX_TYPE#item:List[Tuple[str, List[IndexEntry]]]` — resolved prefix: DOMAIN_INDEX_TYPE; suggestions: []
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r6 comment line 65 expected [66] `DOMAIN_INDEX_TYPE#item:bool` — resolved prefix: DOMAIN_INDEX_TYPE; suggestions: []

### segment `else` names nothing under a resolved prefix (residual) (4)

- [medium] `src/_pytest/reports.py` (43d7e54a41) r21 comment line 369 expected [369, 367] `TestReport.from_item_and_call#if:not call.excinfo/else/if:not isinstance(excinfo, ExceptionInfo)/elif:excinfo.errisinstance(skip.Exception)/else/if:call.when=="call"/else` — resolved prefix: TestReport.from_item_and_call#if:not call.excinfo/else/if:not isinstance(excinfo, ExceptionInfo)/elif:excinfo.errisinstance(skip.Exception); suggestions: ['TestReport.from_item_and_call#if:notcall.excinfo/else/if:notisinstance(excinfo,ExceptionInfo)/elif:excinfo.errisinstance(skip.Exception)/assign:longrepr', 'TestReport.from_item_and_call#if:notcall.excinfo/else/if:notisinstance(excinfo,ExceptionInfo)/elif:excinfo.errisinstance(skip.Exception)/assign:longrepr/item:r.message', 'TestReport.from_item_and_call#if:notcall.excinfo/else/if:notisinstance(excinfo,ExceptionInfo)/elif:excinfo.errisinstance(skip.Exception)/assign:outcome']
- [medium] `seaborn/_oldcore.py` (192af381bf) r20 comment line 152 expected [154] `HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/else` — resolved prefix: HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"/assign:cmap', 'SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"']
- [medium] `seaborn/_oldcore.py` (192af381bf) r42 comment line 334 expected [337] `SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/else` — resolved prefix: SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"', 'SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/assign:size_range', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"']
- [medium] `seaborn/_oldcore.py` (192af381bf) r43 comment line 336 expected [337] `SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/else` — resolved prefix: SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"; suggestions: ['SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"', 'SizeMapping.__init__#if:data.notna().any()/if:map_type=="numeric"/elif:map_type=="categorical"/assign:size_range', 'HueMapping.__init__#if:data.isna().all()/else/if:map_type=="numeric"/elif:map_type=="categorical"']

### symbol path names nothing (attribute/import/local name/typo) (2)

- [medium] `examples/user_interfaces/gtk3_spreadsheet_sgskip.py` (925ea33faa) r5 comment line 56 expected [56] `DataManager.line` — resolved prefix: None; suggestions: ['DataManager.data']
- [medium] `xarray/plot/plot.py` (305405d4e5) r14 comment line 448 expected [449] `_PlotMethods.__doc__` — resolved prefix: None; suggestions: ['_PlotMethods.__call__', '_PlotMethods.__init__', '_PlotMethods.__slots__']

### segment `elif` names nothing under a resolved prefix (residual) (2)

- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r57 comment line 745 expected [746] `print_cycles.recurse#for:referent in referents/if:referent is start/elif:referent is objects or isinstance(referent, types.FrameType)/elif:id(referent) not in all` — resolved prefix: print_cycles.recurse#for:referent in referents/if:referent is start/elif:referent is objects or isinstance(referent, types.FrameType); suggestions: ['print_cycles.recurse#for:referentinreferents/if:referentisstart/elif:referentisobjectsorisinstance(referent,types.FrameType)/continue', 'print_cycles.recurse#for:referentinreferents/if:referentisstart/elif:referentisobjectsorisinstance(referent,types.FrameType)']
- [medium] `pylint/utils/utils.py` (f56fc8eb22) r17 comment line 347 expected [347] `_format_option_value#if:optdict.get("type", None) == "py_version"/elif:isinstance(value, (list, tuple))/elif:isinstance(value, dict)/elif:hasattr(value, "match")` — resolved prefix: _format_option_value#if:optdict.get("type", None) == "py_version"/elif:isinstance(value, (list, tuple)); suggestions: []

### segment `key` names nothing under a resolved prefix (residual) (2)

- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r183 comment line 2177 expected [2177, 2175] `_unikey_or_keysym_to_mplkey#assign:key/key:prior` — resolved prefix: _unikey_or_keysym_to_mplkey; suggestions: ['_unikey_or_keysym_to_mplkey#assign:key~1', '_unikey_or_keysym_to_mplkey#assign:key~2', '_unikey_or_keysym_to_mplkey#assign:key~2/arg:key~1']
- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r184 comment line 2178 expected [2178, 2175] `_unikey_or_keysym_to_mplkey#assign:key/key:next` — resolved prefix: _unikey_or_keysym_to_mplkey; suggestions: ['_unikey_or_keysym_to_mplkey#assign:key~1', '_unikey_or_keysym_to_mplkey#assign:key~2', '_unikey_or_keysym_to_mplkey#assign:key~2/arg:key~1']

### segment `raise` names nothing under a resolved prefix (residual) (1)

- [medium] `astropy/modeling/tabular.py` (bd80ececa9) r10 comment line 278 expected [279] `_Tabular.inverse#if:self.n_inputs == 1/else/raise:NotImplementedError` — resolved prefix: _Tabular.inverse#if:self.n_inputs == 1; suggestions: []

### resolver discriminator contains a comment or backslash continuation (resolver hazard: raw source) (1)

- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r29 comment line 381 expected [381, 380] `strip_math#if:len(s)>=2 and s[0]==s[-1]=="$"/for:tex, plain in [(r"\times", "x"), (r"\mathdefault", ""), (r"\rm", ""), (r"\cal", ""), (r"\tt", ""), (r"\it", ""), ("\\", ""), ("{", ""), ("}", "")]/item:(r"\times", "x")` — resolved prefix: strip_math#if:len(s)>=2 and s[0]==s[-1]=="$"/for:tex, plain in [(r"\times", "x"), (r"\mathdefault", ""), (r"\rm", ""), (r"\cal", ""), (r"\tt", ""), (r"\it", ""), ("\\", ""), ("{", ""), ("}", "")]; suggestions: ['strip_math#if:len(s)>=2ands[0]==s[-1]=="$"/for:tex,plainin[(r"\\times","x"),(r"\\mathdefault",""),(r"\\rm",""),(r"\\cal",""),(r"\\tt/assign:s', 'strip_math#if:len(s)>=2ands[0]==s[-1]=="$"/for:tex,plainin[(r"\\times","x"),(r"\\mathdefault",""),(r"\\rm",""),(r"\\cal",""),(r"\\tt/assign:s/arg:tex', 'strip_math#if:len(s)>=2ands[0]==s[-1]=="$"/for:tex,plainin[(r"\\times","x"),(r"\\mathdefault",""),(r"\\rm",""),(r"\\cal",""),(r"\\tt/assign:s/arg:plain']

### segment `break` names nothing under a resolved prefix (residual) (1)

- [medium] `sphinx/ext/autosummary/__init__.py` (76d99b83e8) r56 comment line 558 expected [559] `extract_summary#if:isinstance(node[0], nodes.section)/elif:not isinstance(node[0], nodes.paragraph)/else/if:len(sentences) == 1/else/for:i in range(len(sentences))/if:summary.endswith(WELL_KNOWN_ABBREVIATIONS)/elif:not any(node.findall(nodes.system_message))/break` — resolved prefix: extract_summary#if:isinstance(node[0], nodes.section)/elif:not isinstance(node[0], nodes.paragraph); suggestions: ['extract_summary#if:isinstance(node[0],nodes.section)/else/if:len(sentences)==1/else/for:iinrange(len(sentences))/if:summary.endswith(WELL_KNOWN_ABBREVIATIONS)/elif:notany(node.findall(nodes.system_message))/break', 'extract_summary#if:isinstance(node[0],nodes.section)/else/if:len(sentences)==1/else/for:iinrange(len(sentences))/if:summary.endswith(WELL_KNOWN_ABBREVIATIONS)/elif:notany(node.findall(nodes.system_message))']

### segment `continue` names nothing under a resolved prefix (residual) (1)

- [medium] `pylint/utils/utils.py` (f56fc8eb22) r11 comment line 205 expected [206] `register_plugins#for:filename in os.listdir(directory)/if:extension in PY_EXTS and base != "__init__" or (not extension and os.path.isdir(/try/except:ValueError/continue` — resolved prefix: register_plugins#for:filename in os.listdir(directory); suggestions: ['register_plugins#for:filenameinos.listdir(directory)/if:extensioninPY_EXTSandbase!="__init__"or(notextensionandos.path.isdir(os.path.joi/try/except:ValueError/continue', 'register_plugins#for:filenameinos.listdir(directory)/if:extensioninPY_EXTSandbase!="__init__"or(notextensionandos.path.isdir(os.path.joi/except:ValueError', 'register_plugins#for:filenameinos.listdir(directory)/if:extensioninPY_EXTSandbase!="__init__"or(notextensionandos.path.isdir(os.path.joi/try/except:ValueError']

### segment `call` names nothing under a resolved prefix (residual) (1)

- [medium] `seaborn/_oldcore.py` (192af381bf) r79 comment line 648 expected [649] `VectorPlotter.__init__#for:var, cls in self._semantic_mappings.items()/call:getattr` — resolved prefix: VectorPlotter.__init__#for:var, cls in self._semantic_mappings.items(); suggestions: ['VectorPlotter.__init__#for:var,clsinself._semantic_mappings.items()/call:setattr', 'VectorPlotter.__init__#for:var,clsinself._semantic_mappings.items()/call:setattr/arg:self', 'VectorPlotter.__init__#for:var,clsinself._semantic_mappings.items()']

### segment `for` names nothing under a resolved prefix (residual) (1)

- [medium] `seaborn/_oldcore.py` (192af381bf) r98 comment line 844 expected [845] `VectorPlotter._assign_variables_wideform#if:empty/elif:flat/else/for:var, attr in self.wide_structure.items()` — resolved prefix: VectorPlotter._assign_variables_wideform#if:empty/elif:flat; suggestions: ['VectorPlotter._assign_variables_wideform#if:empty/else/for:var,attrinself.wide_structure.items()~1', 'VectorPlotter._assign_variables_wideform#if:empty/else/for:var,attrinself.wide_structure.items()~2', 'VectorPlotter._assign_variables_wideform#if:empty/else/for:var,attrinself.wide_structure.items()~2/assign:obj']

## ambiguous (121)


### segment `assign` needs ~n (63)

- [medium] `sympy/core/mul.py` (5fb540a627) r9 comment line 289 expected [290] `Mul.flatten#assign:c_part` — candidates at lines [290, 688]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r10 comment line 290 expected [290] `Mul.flatten#assign:c_part` — candidates at lines [290, 688]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r13 comment line 296 expected [283] `Mul.flatten#assign:c_powers` — candidates at lines [298, 470]; one matches expected: False
- [medium] `sympy/core/mul.py` (5fb540a627) r14 comment line 298 expected [298] `Mul.flatten#assign:c_powers` — candidates at lines [298, 470]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r15 comment line 299 expected [283] `Mul.flatten#assign:num_exp` — candidates at lines [301, 473]; one matches expected: False
- [medium] `sympy/core/mul.py` (5fb540a627) r16 comment line 301 expected [301] `Mul.flatten#assign:num_exp` — candidates at lines [301, 473]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r45 comment line 469 expected [470] `Mul.flatten#assign:c_powers` — candidates at lines [298, 470]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r46 comment line 472 expected [473] `Mul.flatten#assign:num_exp` — candidates at lines [301, 473]; one matches expected: True
- [medium] `sympy/core/mul.py` (5fb540a627) r95 comment line 933 expected [935] `Mul._eval_expand_mul#assign:expr` — candidates at lines [935, 940]; one matches expected: True
- [medium] `astropy/timeseries/periodograms/bls/core.py` (9b21ccf0de) r31 comment line 522 expected [523] `BoxLeastSquares.compute_stats#assign:transit_id` — candidates at lines [523, 529]; one matches expected: True
- [medium] `examples/compose/plot_compare_reduction.py` (ee87033355) r5 comment line 71 expected [72] `<module>#assign:mean_scores` — candidates at lines [70, 72, 74]; one matches expected: True
- [medium] `examples/compose/plot_compare_reduction.py` (ee87033355) r6 comment line 73 expected [74] `<module>#assign:mean_scores` — candidates at lines [70, 72, 74]; one matches expected: True
- [medium] `examples/compose/plot_compare_reduction.py` (ee87033355) r9 comment line 116 expected [117] `<module>#assign:grid` — candidates at lines [66, 117]; one matches expected: True
- [medium] `sklearn/ensemble/forest.py` (b80503d093) r17 comment line 318 expected [322] `BaseForest.fit#if:n_more_estimators < 0/else/assign:trees` — candidates at lines [312, 322]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r8 comment line 240 expected [241] `make_classification#assign:X` — candidates at lines [241, 294, 298]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r9 comment line 244 expected [245] `make_classification#assign:centroids` — candidates at lines [245, 248, 249]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r13 comment line 262 expected [262] `make_classification#for:k, centroid in enumerate(centroids)/assign:X_k` — candidates at lines [262, 267]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r15 comment line 267 expected [267] `make_classification#for:k, centroid in enumerate(centroids)/assign:X_k` — candidates at lines [262, 267]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r25 comment line 429 expected [430] `make_multilabel_classification.sample_example#assign:y` — candidates at lines [430, 435]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r30 comment line 448 expected [449] `make_multilabel_classification.sample_example#assign:cumulative_p_w_sample` — candidates at lines [449, 450]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r55 comment line 1350 expected [1351] `make_sparse_coded_signal#assign:D` — candidates at lines [1351, 1352]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r64 comment line 1535 expected [1536] `make_sparse_spd_matrix#if:norm_diag/assign:d` — candidates at lines [1536, 1537]; one matches expected: True
- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r68 comment line 1722 expected [1723] `make_gaussian_quantiles#assign:X` — candidates at lines [1723, 1727]; one matches expected: True
- [medium] `tutorials/introductory/animation_tutorial.py` (a736580a36) r2 comment line 17 expected [92] `<module>#assign:fig, ax` — candidates at lines [92, 139]; one matches expected: True
- [medium] `tutorials/introductory/animation_tutorial.py` (a736580a36) r6 comment line 124 expected [139] `<module>#assign:fig, ax` — candidates at lines [92, 139]; one matches expected: True
- … 38 more (see report.json)

### segment `call` needs ~n (20)

- [medium] `sympy/core/mul.py` (5fb540a627) r74 comment line 640 expected [641] `Mul.flatten#call:c_part.extend` — candidates at lines [543, 641]; one matches expected: True
- [medium] `examples/cluster/plot_digits_linkage.py` (790dc638b4) r2 comment line 21 expected [24] `<module>#call:print` — candidates at lines [24, 76, 78]; one matches expected: True
- [medium] `examples/cluster/plot_digits_linkage.py` (790dc638b4) r5 comment line 74 expected [76] `<module>#call:print` — candidates at lines [24, 76, 78]; one matches expected: True
- [medium] `tutorials/introductory/animation_tutorial.py` (a736580a36) r7 comment line 155 expected [153] `<module>#call:plt.show` — candidates at lines [121, 153]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r5 comment line 72 expected [74] `<module>#call:ax.annotate` — candidates at lines [63, 65, 67, 74, 80, 90, 120, 137, 164, 169, 175, 181, 187, 193, 199, 206, 214, 238, 246, 256, 266]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r6 comment line 86 expected [90] `<module>#call:ax.annotate` — candidates at lines [63, 65, 67, 74, 80, 90, 120, 137, 164, 169, 175, 181, 187, 193, 199, 206, 214, 238, 246, 256, 266]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r21 comment line 315 expected [318] `<module>#call:ax1.annotate` — candidates at lines [318, 324, 330, 336]; one matches expected: True
- [medium] `tutorials/intermediate/imshow_extent.py` (8065a06714) r9 comment line 164 expected [171] `<module>#call:generate_imshow_demo_grid` — candidates at lines [171, 258]; one matches expected: True
- [medium] `tutorials/intermediate/imshow_extent.py` (8065a06714) r11 comment line 232 expected [258] `<module>#call:generate_imshow_demo_grid` — candidates at lines [171, 258]; one matches expected: True
- [medium] `django/db/backends/mysql/introspection.py` (fc7ce178fd) r3 comment line 63 expected [68] `DatabaseIntrospection.get_table_description#call:cursor.execute` — candidates at lines [68, 75]; one matches expected: True
- [medium] `django/db/backends/mysql/introspection.py` (fc7ce178fd) r12 comment line 208 expected [209] `DatabaseIntrospection.get_constraints#call:cursor.execute` — candidates at lines [181, 201, 209]; one matches expected: True
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r110 comment line 1347 expected [1348] `setup#call:app.add_config_value` — candidates at lines [1348, 1349, 1350, 1351, 1354, 1355, 1356, 1357, 1358, 1359, 1360, 1361, 1362, 1363, 1364, 1365, 1366, 1367, 1368, 1369, 1370, 1371, 1372, 1373, 1374, 1375, 1376, 1377, 1378, 1379, 1380, 1381, 1382, 1383, 1384, 1385, 1386, 1387, 1388, 1390, 1391]; one matches expected: True
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r111 comment line 1393 expected [1394] `setup#call:app.add_event` — candidates at lines [1394, 1395]; one matches expected: True
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r112 comment line 1397 expected [1398] `setup#call:app.connect` — candidates at lines [1398, 1399, 1400, 1401, 1402, 1403, 1404, 1405, 1406, 1407, 1408]; one matches expected: True
- [medium] `sphinx/domains/python.py` (3fda527035) r51 comment line 1071 expected [1073] `PyModule.run#if:not noindex/call:ret.append` — candidates at lines [1073, 1076]; one matches expected: True
- [medium] `src/_pytest/warnings.py` (3360aea9cc) r3 comment line 78 expected [79] `catch_warnings_for_item#with:warnings.catch_warnings(record=True)/if:not sys.warnoptions/call:warnings.filterwarnings` — candidates at lines [79, 80]; one matches expected: True
- [medium] `src/_pytest/main.py` (96ead8509d) r3 comment line 128 expected [130] `pytest_addoption#call:group.addoption` — candidates at lines [105, 110, 116, 122, 130, 138, 145, 153, 162]; one matches expected: True
- [medium] `requests/sessions.py` (9eaa36ae43) r20 comment line 173 expected [176] `SessionRedirectMixin.resolve_redirects#while:resp.is_redirect/call:extract_cookies_to_jar` — candidates at lines [176, 198]; one matches expected: True
- [medium] `requests/sessions.py` (9eaa36ae43) r56 comment line 544 expected [546] `Session.send#call:kwargs.setdefault` — candidates at lines [546, 547, 548, 549]; one matches expected: True
- [medium] `seaborn/relational.py` (fa8b3583b3) r20 comment line 381 expected [390] `_LinePlotter.plot#call:kws.setdefault` — candidates at lines [390, 391]; one matches expected: True

### segment `if` needs ~n (12)

- [medium] `sklearn/linear_model/_glm/_newton_solver.py` (d624d1399b) r21 comment line 307 expected [315] `NewtonSolver.check_convergence#if:self.verbose` — candidates at lines [305, 316, 326, 331]; one matches expected: True
- [medium] `pylint/checkers/variables.py` (cc103e894a) r34 comment line 616 expected [617] `NamesConsumer.get_next_to_consume#if:found_nodes` — candidates at lines [617, 627, 637, 649]; one matches expected: True
- [medium] `pylint/checkers/variables.py` (cc103e894a) r35 comment line 625 expected [627] `NamesConsumer.get_next_to_consume#if:found_nodes` — candidates at lines [617, 627, 637, 649]; one matches expected: True
- [medium] `pylint/checkers/variables.py` (cc103e894a) r36 comment line 635 expected [637] `NamesConsumer.get_next_to_consume#if:found_nodes` — candidates at lines [617, 627, 637, 649]; one matches expected: True
- [medium] `pylint/checkers/variables.py` (cc103e894a) r37 comment line 647 expected [649] `NamesConsumer.get_next_to_consume#if:found_nodes` — candidates at lines [617, 627, 637, 649]; one matches expected: True
- [medium] `xarray/plot/plot.py` (305405d4e5) r25 comment line 678 expected [680] `_plot2d.newplotfunc#if:imshow_rgb` — candidates at lines [621, 680]; one matches expected: True
- [medium] `seaborn/utils.py` (a4887b2c42) r33 comment line 430 expected [431] `move_legend#if:isinstance(obj, Grid)` — candidates at lines [431, 482]; one matches expected: True
- [medium] `seaborn/utils.py` (a4887b2c42) r40 comment line 481 expected [482] `move_legend#if:isinstance(obj, Grid)` — candidates at lines [431, 482]; one matches expected: True
- [medium] `seaborn/regression.py` (1c7d804e26) r32 comment line 342 expected [343] `_RegressionPlotter.plot#if:self.scatter` — candidates at lines [343, 364]; one matches expected: True
- [medium] `seaborn/regression.py` (1c7d804e26) r36 comment line 363 expected [364] `_RegressionPlotter.plot#if:self.scatter` — candidates at lines [343, 364]; one matches expected: True
- [medium] `seaborn/_oldcore.py` (192af381bf) r62 comment line 502 expected [503] `SizeMapping.numeric_mapping#if:isinstance(sizes, dict)` — candidates at lines [435, 503]; one matches expected: True
- [medium] `src/flask/app.py` (3bbe1bb229) r61 comment line 1048 expected [1050] `Flask.add_url_rule#if:provide_automatic_options is None` — candidates at lines [1050, 1055]; one matches expected: True

### segment `try` needs ~n (11)

- [medium] `sympy/core/assumptions.py` (34d5d51389) r17 comment line 516 expected [533] `_ask#try` — candidates at lines [533, 539]; one matches expected: True
- [medium] `sympy/core/assumptions.py` (34d5d51389) r18 comment line 538 expected [539] `_ask#try` — candidates at lines [533, 539]; one matches expected: True
- [medium] `astropy/io/fits/convenience.py` (59baeb14ff) r44 comment line 864 expected [865] `printdiff#if:isinstance(inputa, str) and has_extensions/try` — candidates at lines [865, 871]; one matches expected: True
- [medium] `sphinx/ext/autosummary/__init__.py` (76d99b83e8) r19 comment line 342 expected [343] `Autosummary.get_items#for:name in names/try` — candidates at lines [314, 343, 356]; one matches expected: True
- [medium] `sphinx/ext/autosummary/__init__.py` (76d99b83e8) r22 comment line 354 expected [356] `Autosummary.get_items#for:name in names/try` — candidates at lines [314, 343, 356]; one matches expected: True
- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r88 comment line 1080 expected [1081] `StandaloneHTMLBuilder.handle_page#try` — candidates at lines [1081, 1091, 1096, 1111]; one matches expected: True
- [medium] `xarray/plot/plot.py` (305405d4e5) r40 comment line 863 expected [864] `imshow#try` — candidates at lines [864, 869]; one matches expected: True
- [medium] `src/_pytest/main.py` (96ead8509d) r32 comment line 685 expected [687] `Session._tryconvertpyarg#try` — candidates at lines [678, 687]; one matches expected: True
- [medium] `requests/__init__.py` (35987f956b) r3 comment line 51 expected [52] `<module>#try` — candidates at lines [52, 71]; one matches expected: True
- [medium] `requests/__init__.py` (35987f956b) r5 comment line 71 expected [71] `<module>#try` — candidates at lines [52, 71]; one matches expected: True
- [medium] `src/flask/cli.py` (37a15ff2d8) r11 comment line 117 expected [119] `find_app_by_string#try` — candidates at lines [119, 154]; one matches expected: True

### segment `arg` needs ~n (7)

- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r8 comment line 121 expected [121, 120] `<module>#call:ax.annotate/arg:xy` — candidates at lines [64, 66, 68, 75, 81, 91, 121, 138, 165, 170, 176, 182, 188, 194, 200, 207, 215, 239, 247, 257, 267]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r9 comment line 122 expected [122, 120] `<module>#call:ax.annotate/arg:xytext` — candidates at lines [76, 82, 92, 122, 139, 166, 171, 177, 183, 189, 195, 201, 208, 216, 240, 248, 258, 268]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r11 comment line 138 expected [138, 137] `<module>#call:ax.annotate/arg:xy` — candidates at lines [64, 66, 68, 75, 81, 91, 121, 138, 165, 170, 176, 182, 188, 194, 200, 207, 215, 239, 247, 257, 267]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r12 comment line 139 expected [139, 137] `<module>#call:ax.annotate/arg:xytext` — candidates at lines [76, 82, 92, 122, 139, 166, 171, 177, 183, 189, 195, 201, 208, 216, 240, 248, 258, 268]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r17 comment line 250 expected [251] `<module>#call:ax.annotate/arg:arrowprops` — candidates at lines [77, 83, 124, 142, 167, 172, 178, 184, 190, 196, 203, 211, 218, 242, 251, 261, 271]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r18 comment line 260 expected [261] `<module>#call:ax.annotate/arg:arrowprops` — candidates at lines [77, 83, 124, 142, 167, 172, 178, 184, 190, 196, 203, 211, 218, 242, 251, 261, 271]; one matches expected: True
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r19 comment line 270 expected [271] `<module>#call:ax.annotate/arg:arrowprops` — candidates at lines [77, 83, 124, 142, 167, 172, 178, 184, 190, 196, 203, 211, 218, 242, 251, 261, 271]; one matches expected: True

### segment `import` needs ~n (3)

- [medium] `sklearn/datasets/_samples_generator.py` (bc2cf1bcb5) r2 comment line 5 expected [9] `<module>#import:numbers` — candidates at lines [9, 10]; one matches expected: True
- [medium] `sphinx/util/inspect.py` (c730fefdb6) r2 comment line 26 expected [26] `<module>#import:sphinx.pycode.ast` — candidates at lines [26, 27]; one matches expected: True
- [medium] `requests/sessions.py` (9eaa36ae43) r2 comment line 36 expected [37] `<module>#import:.models` — candidates at lines [19, 37]; one matches expected: True

### segment `for` needs ~n (2)

- [medium] `pylint/lint/pylinter.py` (53345a6b17) r62 comment line 793 expected [794] `PyLinter._astroid_module_checker#for:c in _checkers` — candidates at lines [794, 813]; one matches expected: True
- [medium] `pylint/lint/pylinter.py` (53345a6b17) r63 comment line 812 expected [813] `PyLinter._astroid_module_checker#for:c in _checkers` — candidates at lines [794, 813]; one matches expected: True

### segment `return` needs ~n (1)

- [medium] `sphinx/util/inspect.py` (c730fefdb6) r59 comment line 469 expected [470] `is_builtin_class_method#try/except:AttributeError/return` — candidates at lines [470, 480]; one matches expected: True

### segment `pass` needs ~n (1)

- [medium] `sphinx/builders/html/__init__.py` (64a5c1f604) r90 comment line 1085 expected [1089] `StandaloneHTMLBuilder.handle_page#try/except:AttributeError/pass` — candidates at lines [1089, 1094]; one matches expected: True

### symbol path (F1/F2 rebinding) (1)

- [medium] `pylint/utils/utils.py` (f56fc8eb22) r12 docstring line 270 expected [265] `get_global_option` — candidates at lines [216, 223, 230, 239, 248, 257, 265]; one matches expected: True

## wrong_place (9)


### lead comment attached to a distant statement (5)

- [medium] `sympy/core/mul.py` (5fb540a627) r17 comment line 302 expected [283] `Mul.flatten#assign:neg1e` — resolved line 304, distance 21
- [medium] `sympy/core/mul.py` (5fb540a627) r20 comment line 307 expected [283] `Mul.flatten#assign:order_symbols` — resolved line 309, distance 26
- [medium] `sympy/core/mul.py` (5fb540a627) r57 comment line 538 expected [522] `Mul.flatten#for:b, e in num_exp` — resolved line 539, distance 17
- [medium] `sklearn/linear_model/_glm/_newton_solver.py` (d624d1399b) r16 comment line 247 expected [253] `NewtonSolver.line_search#for:i in range(21)/assign:self.loss_value, self.gradient` — resolved line 238, distance 15
- [medium] `sklearn/linear_model/_glm/_newton_solver.py` (d624d1399b) r29 comment line 386 expected [394] `NewtonSolver.solve#while:self.iteration <= self.max_iter and not self.converged/call:self.update_gradient_hessian` — resolved line 384, distance 10

### hoisted to the enclosing statement (comment sits on an element inside it) (3)

- [medium] `django/db/models/sql/compiler.py` (eda7fc3b5e) r64 comment line 1033 expected [1034] `SQLCompiler.get_select_for_update_of_arguments._get_parent_klass_info#for:parent_model, parent_link in concrete_model._meta.parents.items()/yield` — resolved line 1026, distance 8
- [medium] `sphinx/transforms/__init__.py` (f854f17720) r14 comment line 136 expected [137] `MoveModuleTargets.apply#for:node in self.document.traverse(nodes.target)/if:'ismod' in node and node.parent.__class__ is nodes.section and node.parent.index(node) == 1` — resolved line 134, distance 3
- [medium] `xarray/util/print_versions.py` (96983c83aa) r4 comment line 47 expected [48] `get_sys_info#try/call:blob.extend` — resolved line 41, distance 7

### symbol anchor for a comment (points at first binding / definition) (1)

- [medium] `src/_pytest/python.py` (18d9098553) r42 comment line 797 expected [801] `Instance._ALLOW_MARKERS` — resolved line 796, distance 5

## dropped (0)


## kind_mismatch (14)


### post -> lead (5)

- [medium] `sympy/core/mul.py` (5fb540a627) r13 comment line 296 expected [283] `Mul.flatten#assign:c_powers` — predicted kind lead
- [medium] `sympy/core/mul.py` (5fb540a627) r15 comment line 299 expected [283] `Mul.flatten#assign:num_exp` — predicted kind lead
- [medium] `sympy/core/mul.py` (5fb540a627) r17 comment line 302 expected [283] `Mul.flatten#assign:neg1e` — predicted kind lead
- [medium] `sympy/core/mul.py` (5fb540a627) r20 comment line 307 expected [283] `Mul.flatten#assign:order_symbols` — predicted kind lead
- [medium] `sympy/core/mul.py` (5fb540a627) r57 comment line 538 expected [522] `Mul.flatten#for:b, e in num_exp` — predicted kind lead

### lead -> post (4)

- [medium] `sklearn/linear_model/_glm/_newton_solver.py` (d624d1399b) r16 comment line 247 expected [253] `NewtonSolver.line_search#for:i in range(21)/assign:self.loss_value, self.gradient` — predicted kind post
- [medium] `sklearn/linear_model/_glm/_newton_solver.py` (d624d1399b) r21 comment line 307 expected [315] `NewtonSolver.check_convergence#if:self.verbose` — predicted kind post
- [medium] `examples/text_labels_and_annotations/annotation_demo.py` (92958dde25) r24 comment line 348 expected [349] `<module>#assign:an1/arg:bbox` — predicted kind post
- [medium] `src/_pytest/python.py` (18d9098553) r42 comment line 797 expected [801] `Instance._ALLOW_MARKERS` — predicted kind post

### todo -> lead (3)

- [medium] `sympy/core/mul.py` (5fb540a627) r24 comment line 330 expected [330] `Mul.flatten#for:o in seq/if:o.is_Mul/if:o.is_commutative/call:seq.extend` — predicted kind lead
- [medium] `astropy/io/fits/fitsrec.py` (f82a0ee516) r34 comment line 422 expected [426] `FITS_rec.from_columns#for:idx, column in enumerate(columns)/if:isinstance(recformat, _FormatX)/elif:isinstance(columns, _AsciiColDefs)/if:fitsformat._pseudo_logical/assign:outarr` — predicted kind lead
- [medium] `src/_pytest/python.py` (18d9098553) r8 comment line 265 expected [267] `PyobjMixin.obj~1#if:obj is None/if:self._ALLOW_MARKERS` — predicted kind lead

### todo -> trail (2)

- [medium] `lib/matplotlib/cbook.py` (c9699b2e21) r70 comment line 946 expected [946] `delete_masked_points#for:i, x in enumerate(margs)/if:seqlist[i]/try/except:Exception` — predicted kind trail
- [medium] `src/_pytest/python.py` (18d9098553) r41 comment line 796 expected [796] `Instance._ALLOW_MARKERS` — predicted kind trail
