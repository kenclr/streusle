#!/usr/bin/env python3
"""
Query by token

Interface: ./tquery [-I] streusle.json <prefix><fldname><op><pattern>+

prefix: + to print the value of the field in a column of output, empty otherwise

fldname: one of the column names: w(ord), l(emma), upos, xpos, feats, head, deprel, edeps, misc, smwe, wmwe, lt (lextag)
or lc (lexcat), ll (lexlemma), ss = r (role), f (function)
g (governor lemma), o (object lemma), config (syntactic configuration). Can also specify a token-level property of the governor or object:
g.upos, o.lt, etc. (not currently supported for role/function/lexlemma/lexcat, which are stored at the lexical level; cannot be used recursively).

op: if filtering on the field, one of: = (regex partial match), == (regex full match), != (inverse regex partial match), !== (inverse regex full match)

pattern: if filtering on the field, regex to match against the field's value; case-insensitive unless -I is specified

Note that for prepositions/possessives, lextag contains the full supersense labeling in "role|function" notation. 
So lextag can be used to search for a supersense without specifying whether it occurs as role or function.

@author: Nathan Schneider (@nschneid)
@since: 2018-06-13
"""

import sys, json, fileinput, re
from itertools import chain

TKN_LEVEL_FIELDS = {'w': 'word', 'word': 'word', 'l': 'lemma', 'lemma': 'lemma', 
                   'upos': 'upos', 'xpos': 'xpos', 'feats': 'feats', 
                   'head': 'head', 'deprel': 'deprel', 'edeps': 'edeps', 
                   'misc': 'misc', 'smwe': 'smwe', 'wmwe': 'wmwe', 'lextag': 'lextag', 'lt': 'lextag'}
LEX_LEVEL_FIELDS = {'lexcat': 'lexcat', 'lc': 'lexcat', 'lexlemma': 'lexlemma', 'll': 'lexlemma', 'r': 'ss', 'ss': 'ss', 'f': 'ss2', 'ss2': 'ss2'}
GOVOBJ_FIELDS = {'g': 'govlemma', 'govlemma': 'govlemma', 'o': 'objlemma', 'objlemma': 'objlemma', 'config': 'config'}
ALL_FIELDS = dict(**TKN_LEVEL_FIELDS, **LEX_LEVEL_FIELDS, **GOVOBJ_FIELDS)
RE_FLAGS = re.IGNORECASE   # case-insensitive by default

args = sys.argv[1:]
assert len(args)>=2

if args[0].startswith('-'):
    flag = args.pop(0)
    if flag=='-I': # case-sensitive
        RE_FLAGS = 0

inFP = args.pop(0)
constraints = tknconstraints, lexconstraints, govobjconstraints = [], [], []
prints = [] # fields whose values are to be printed
for arg in args:
    printme = False
    if arg.startswith('+'):
        printme = True
        arg = arg[1:]
        
    if '=' in arg:
        fld, pattern = arg.split('=', 1)
    
        if fld.endswith('!'):
            op = '!='
            fld = fld[:-1]
            if pattern.startswith('='):
                op += '='
                pattern = '^' + pattern[1:] + '$'
            r = re.compile(pattern, RE_FLAGS)
            matchX = (lambda r: lambda s: s is not None and r.search(s) is None)(r)
        elif pattern.startswith('='):
            op = '=='
            pattern = pattern[1:]
            r = re.compile('^'+pattern+'$', RE_FLAGS)
            matchX = (lambda r: lambda s: s is not None and r.search(s) is not None)(r)
        else:
            op = '='
            r = re.compile(pattern, RE_FLAGS)
            matchX = (lambda r: lambda s: s is not None and r.search(s) is not None)(r)
    
        if '.' in fld:
            prefix, fld = fld.split('.',1)
            prefix += '.'   # g. (governor) or o. (object)
        else:
            prefix = ''
        fld = ALL_FIELDS[fld]
        fld = prefix+fld
        if fld in TKN_LEVEL_FIELDS:
            tknconstraints.append((fld, matchX))
        elif fld in LEX_LEVEL_FIELDS:
            lexconstraints.append((fld, matchX))
        else:
            govobjconstraints.append((fld, matchX))
    else:
        assert printme
        fld = arg
        
    if printme:
        if '.' in fld:
            prefix, fld = fld.split('.',1)
            prefix += '.'   # g. (governor) or o. (object)
        else:
            prefix = ''
        fld = ALL_FIELDS[fld]
        fld = prefix+fld
        if fld not in prints:
            prints.append(fld)
        # to the "constraints", add a dummy item indicate that the field should be looked up for printing
        if fld in TKN_LEVEL_FIELDS:
            tknconstraints.append((fld, None))
        elif fld in LEX_LEVEL_FIELDS:
            lexconstraints.append((fld, None))
        else:
            govobjconstraints.append((fld, None))


with open(inFP, encoding='utf-8') as inF:
    data = json.load(inF)

n = 0
for sent in data:
    for lexe in chain(sent["swes"].values(), sent["smwes"].values()):
        fail = False
        myprints = {k: None for k in prints}
        # at the lexical expression level: lexcat, lexlemma, ss (role), ss2 (function), heuristic_relation["govlemma", "objlemma", "config"]
        for fld, matchX in lexconstraints:
            if matchX and not matchX(lexe[fld]):
                fail = True
                break
            if matchX is None:
                myprints[fld] = lexe[fld]
        if govobjconstraints and not fail:
            if "heuristic_relation" not in lexe:
                fail = True
            else:
                govobj = lexe["heuristic_relation"]
                for fld, matchX in govobjconstraints:
                    if '.' in fld:
                        assert fld.startswith('g.') or fld.startswith('o.')
                        i = govobj["gov"] if fld.startswith('g.') else govobj["obj"]
                        if i is None:
                            if matchX:
                                fail = True
                                break
                            else:
                                go = {'': ''}
                                f = ''
                        else:
                            go = sent["toks"][i-1]
                            f = fld.split('.',1)[1]
                    else:
                        go = govobj
                        f = fld
                    
                    if matchX and not matchX(go[f]):
                        fail = True
                        break
                    if matchX is None:
                        myprints[fld] = go[f]
        if tknconstraints and not fail:
            toks = [sent["toks"][i-1] for i in lexe["toknums"]]
            for fld, matchX in tknconstraints:
                if matchX and not any(matchX(tok[fld]) for tok in toks):
                    fail = True
                    break
                if matchX is None:
                    myprints[fld] = tuple(tok[fld] for tok in toks)
        
        if not fail:
            s = ''
            inmatch = False
            for tok in sent["toks"]:
                if tok["#"] in lexe["toknums"]:
                    if not inmatch:
                        inmatch = True
                        s += '>> '
                else:
                    if inmatch:
                        inmatch = False
                        s += '<< '
                s += tok["word"] + ' '
            
            print(sent["sent_id"], 
                  *[myprints[f] for f in prints],
                  #lexe["ss"]+('|'+lexe["ss2"] if lexe["ss2"] and lexe["ss2"]!=lexe["ss"] else ''),     # TODO: make a field for this
                  s, sep='\t')
            n += 1

print(f'{n} match' + ('es' if n!=1 else ''), prints, file=sys.stderr)
