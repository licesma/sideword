## Documentation in this repository

The Python source in this repository carries no comments or docstrings. Its
documentation is stored separately, as records keyed to anchors. An anchor is a
symbol path such as `Cart.add`, optionally followed by `#` and a path of segments
naming a place inside that symbol, such as `Cart.add#assign:self.total`.

The `sideword` command reads it. File paths are repository-relative.

    sideword index <file.py>
        One line per documented anchor in that file: the anchor, its kind, and its
        length in lines. The header gives the record count and a token estimate for
        the whole file's documentation. A file with nothing documented prints the
        header and no rows.

    sideword show <file.py> <anchor>
        The documentation for that one anchor. Exits non-zero if the anchor is not
        documented. When several records share an anchor, all of them print, each
        under its heading; `--kind` selects one.

    sideword search <pattern> [path ...]
        Records whose text matches the regular expression `pattern`: one line each,
        giving the file, the anchor, and the matched line. `-i` ignores case. An
        optional path limits the search to a file or directory.
