# -*- coding: utf-8 -*-
"""Build, commit and push — the one command that puts a change on the phones.

    python src/deploy.py "what changed"

GitHub Pages redeploys within a minute or two of the push. An open app sees
the new service worker and offers "יש גרסה חדשה · רענן"; a closed one simply
opens on the new version next time it has a connection.
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(*cmd, check=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if check and r.returncode != 0:
        sys.exit('failed: %s\n%s%s' % (' '.join(cmd), r.stdout, r.stderr))
    return r.stdout.strip()


if len(sys.argv) < 2 or not sys.argv[1].strip():
    sys.exit('usage: python src/deploy.py "what changed"')

run(sys.executable, os.path.join(HERE, 'build.py'))
run('git', 'add', '-A')
if not run('git', 'status', '--porcelain'):
    print('nothing changed — nothing to deploy')
    sys.exit(0)
print(run('git', 'diff', '--cached', '--stat'))
run('git', '-c', 'user.name=Itzik', '-c', 'user.email=itzikglanz@gmail.com',
    'commit', '-q', '-m', sys.argv[1].strip() + '\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')
run('git', 'push', '-q')
print('pushed', run('git', 'log', '--oneline', '-1'))
print('live in ~1-2 min: https://itzikglanz87.github.io/fifa-tournament/')
