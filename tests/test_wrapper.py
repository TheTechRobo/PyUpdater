# --------------------------------------------------------------------------
# Copyright 2014 Digital Sapphire Development Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# --------------------------------------------------------------------------
from __future__ import unicode_literals

import os

import pytest

from pyupdater.wrapper import (_build, clean,
                               keys, _make_spec,
                               pkg, update)
from pyupdater.wrapper.options import (add_build_parser,
                                       add_clean_parser,
                                       add_keys_parser,
                                       add_make_spec_parser,
                                       add_package_parser,
                                       add_update_parser,
                                       make_subparser)


@pytest.mark.usefixtures('cleandir', 'parser', 'pyu')
class TestBuilder(object):

    def test_build_no_options(self, parser):
        subparser = make_subparser(parser)
        add_build_parser(subparser)
        with pytest.raises(SystemExit):
            parser.parse_known_args(['build'])

    def test_build_no_appanme(self, parser):
        subparser = make_subparser(parser)
        add_build_parser(subparser)
        with pytest.raises(SystemExit):
            parser.parse_known_args(['build', '--app-version=0.2.10'])

    def test_build_no_appversion(self, parser):
        subparser = make_subparser(parser)
        add_build_parser(subparser)
        with pytest.raises(SystemExit):
            parser.parse_known_args(['build', '--app-name=Test'])

    def test_build_no_arguments(self, parser, pyu):
        pyu.setup()
        pyu.make_keys(3)
        subparser = make_subparser(parser)
        add_build_parser(subparser)
        with pytest.raises(SystemExit):
            with open('app.py', 'w') as f:
                f.write('print "Hello World"')
            opts, other = parser.parse_known_args(['build', 'app.py'])
            _build(opts, other)

    def test_build(self, parser, pyu):
        pyu.setup()
        pyu.make_keys(3)
        subparser = make_subparser(parser)
        add_build_parser(subparser)
        with open('app.py', 'w') as f:
            f.write('print "Hello World"')

        build_cmd = ['build', '-F', '--app-name=Test',
                     '--app-version=0.1.0', 'app.py']
        build_cmd = [str(b) for b in build_cmd]
        opts, other = parser.parse_known_args(build_cmd)
        _build(opts, other)


@pytest.mark.usefixtures('cleandir', 'parser')
class TestClean(object):

    def test_no_args(self, parser):
        subparser = make_subparser(parser)
        add_clean_parser(subparser)
        assert parser.parse_known_args(['clean'])

    def test_execution(self, parser):
        update_folder = 'pyu-data'
        data_folder = '.pyupdater'
        subparser = make_subparser(parser)
        add_clean_parser(subparser)
        os.mkdir(update_folder)
        os.mkdir(data_folder)
        args, other = parser.parse_known_args(['clean', '-y'])
        clean(args)
        assert not os.path.exists(update_folder)
        assert not os.path.exists(data_folder)

    def test_execution_no_clean(self, parser):
        update_folder = 'pyu-data'
        data_folder = '.pyupdater'
        subparser = make_subparser(parser)
        add_clean_parser(subparser)
        args, other = parser.parse_known_args(['clean', '-y'])
        clean(args)
        assert not os.path.exists(update_folder)
        assert not os.path.exists(data_folder)


@pytest.mark.usefixtures('cleandir', 'parser')
class TestKeys(object):

    def test_no_options(self, parser):
        subparser = make_subparser(parser)
        add_keys_parser(subparser)
        assert parser.parse_known_args(['keys'])

    def test_revoke(self, parser):
        subparser = make_subparser(parser)
        add_keys_parser(subparser)
        cmd = ['keys', '-y']
        opts, other = parser.parse_known_args(cmd)

    def test_revoke_count(self, parser):
        subparser = make_subparser(parser)
        add_keys_parser(subparser)
        cmd = ['keys', '-y', '--count=3']
        opts, other = parser.parse_known_args(cmd)


@pytest.mark.usefixtures('cleandir', 'parser', 'pyu')
class TestMakeSpec(object):

    def test_no_options(self, parser):
        subparser = make_subparser(parser)
        add_make_spec_parser(subparser)
        with pytest.raises(SystemExit):
            assert parser.parse_known_args(['make-spec'])

    def test_execution(self, parser, pyu):
        pyu.setup()
        pyu.make_keys(3)
        subparser = make_subparser(parser)
        add_make_spec_parser(subparser)
        with open('app.py', 'w') as f:
            f.write('print "Hello World"')
        opts, other = parser.parse_known_args(['make-spec', '-F',
                                               '--app-name=Test',
                                               '--app-version=0.1.0',
                                               'app.py'])
        _make_spec(opts, other)


@pytest.mark.usefixtures('cleandir', 'parser', 'pyu', 'db')
class TestPkg(object):

    def test_no_options(self, parser, pyu, db):
        subparser = make_subparser(parser)
        add_package_parser(subparser)
        pyu.update_config(pyu.config, db)
        pyu.setup()
        pyu.make_keys(3)
        db._sync_db()
        opts, other = parser.parse_known_args(['pkg'])
        with pytest.raises(SystemExit):
            pkg(opts)

    def test_execution(self, parser, pyu, db):
        subparser = make_subparser(parser)
        add_package_parser(subparser)
        pyu.update_config(pyu.config, db)
        pyu.setup()
        pyu.make_keys(3)
        db._sync_db()
        cmd = ['pkg', '-P', '-S']
        opts, other = parser.parse_known_args(cmd)
        pkg(opts)


@pytest.mark.usefixtures('cleandir', 'parser', 'pyu', 'db')
class TestUpdateRepo(object):

    def test_no_options(self, parser, pyu, db):
        pyu.update_config(pyu.config, db)
        pyu.setup()
        pyu.make_keys(3)
        db._sync_db()
        subparser = make_subparser(parser)
        add_update_parser(subparser)
        opts, other = parser.parse_known_args(['update'])
        update(opts)
