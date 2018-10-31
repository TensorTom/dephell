from operator import attrgetter
from tomlkit import parse, aot, table, document, dumps, inline_table
from ..models import Dependency, RootDependency, Constraint
from ..repositories import get_repo
from .base import BaseConverter


VCS_LIST = ('git', 'svn', 'hg', 'bzr')


class PIPFileConverter(BaseConverter):
    lock = False

    def loads(self, content) -> RootDependency:
        doc = parse(content)
        deps = []
        root = RootDependency()
        if 'packages' in doc:
            for name, content in doc['packages'].items():
                deps.append(self._make_dep(root, name, content))
        root.attach_dependencies(deps)
        return root

    def dumps(self, graph) -> str:
        doc = document()
        source = table()
        source['url'] = 'https://pypi.python.org/simple'
        source['verify_ssl'] = True
        source['name'] = 'pypi'
        sources = aot()
        sources.append(source)
        doc.add('source', sources)

        deps = table()
        for dep in sorted(graph):
            if not dep.used:
                continue
            deps[dep.name] = self._format_dep(dep)
        doc.add('packages', deps)

        return dumps(doc)

    # https://github.com/pypa/pipfile/blob/master/examples/Pipfile
    @staticmethod
    def _make_dep(root, name: str, content) -> Dependency:
        """
        Fields:
            ref
            vcs
            editable
            extras
            markers
            index
            hashes

            subdirectory
            path
            file
            uri
            git, svn, hg, bzr
        """
        if isinstance(content, str):
            return Dependency(
                raw_name=name,
                constraint=Constraint(root, content),
                repo=get_repo(),
            )

        # get link
        url = content.get('file') or content.get('path') or content.get('vcs')
        if not url:
            for vcs in VCS_LIST:
                if vcs in content:
                    url = vcs + '+' + content[vcs]
                    break
        if 'ref' in content:
            url += '@' + content['ref']

        # https://github.com/sarugaku/requirementslib/blob/master/src/requirementslib/models/requirements.py
        # https://github.com/pypa/pipenv/blob/master/pipenv/project.py
        return Dependency.from_params(
            raw_name=name,
            # https://github.com/sarugaku/requirementslib/blob/master/src/requirementslib/models/utils.py
            constraint=Constraint(root, content.get('version', '')),
            extras=set(content.get('extras', [])),
            marker=content.get('markers'),
            url=url,
        )

    def _format_dep(self, dep: Dependency, *, short: bool=True):
        if self.lock:
            release = dep.group.best_release

        result = inline_table()

        if self.lock:
            result['version'] = '==' + str(release.version)
        else:
            result['version'] = str(dep.constraint) or '*'

        if dep.extras:
            result['extras'] = list(sorted(dep.extras))
        if dep.marker:
            result['markers'] = str(dep.marker)

        if self.lock:
            result['hashes'] = []
            for digest in release.hashes:
                result['hashes'].append('sha256:' + digest)

        # if we have only version, return string instead of table
        if short and tuple(result.value) == ('version', ):
            return result['version']

        # do not specify version explicit
        if result['version'] == '*':
            del result['version']

        return result