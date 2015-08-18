#-----------------------------------------------------------------------------
# Copyright (c) 2005-2015, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License with exception
# for distributing bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------



#--- functions for checking guts ---
# NOTE: By GUTS it is meant intermediate files and data structures that
# PyInstaller creates for bundling files and creating final executable.
import hashlib
import os
import platform
import shutil
import sys

from PyInstaller import is_darwin, is_win, compat
from PyInstaller.compat import EXTENSION_SUFFIXES
from PyInstaller.depend import dylib
from PyInstaller.utils import misc
from PyInstaller.utils.misc import load_py_data_struct, save_py_data_struct
from .. import log as logging

if is_win:
    from PyInstaller.utils.win32 import winmanifest, winresource

logger = logging.getLogger(__name__)


#-- Helpers for checking guts.
#
# NOTE: By _GUTS it is meant intermediate files and data structures that
# PyInstaller creates for bundling files and creating final executable.

def _check_guts_eq(attr, old, new, last_build):
    """
    rebuild is required if values differ
    """
    if old != new:
        logger.info("Building because %s changed", attr)
        return True
    return False


def _check_guts_toc_mtime(attr, old, toc, last_build, pyc=0):
    """
    rebuild is required if mtimes of files listed in old toc are newer
    than last_build

    if pyc=1, check for .py files, too

    Use this for calculated/analysed values read from cache.
    """
    for (nm, fnm, typ) in old:
        if misc.mtime(fnm) > last_build:
            logger.info("Building because %s changed", fnm)
            return True
        elif pyc and misc.mtime(fnm[:-1]) > last_build:
            logger.info("Building because %s changed", fnm[:-1])
            return True
    return False


def _check_guts_toc(attr, old, toc, last_build, pyc=0):
    """
    rebuild is required if either toc content changed or mtimes of
    files listed in old toc are newer than last_build

    if pyc=1, check for .py files, too

    Use this for input parameters.
    """
    return (_check_guts_eq(attr, old, toc, last_build)
            or _check_guts_toc_mtime(attr, old, toc, last_build, pyc=pyc))


#---

def add_suffix_to_extensions(toc):
    """
    Returns a new TOC with proper library suffix for EXTENSION items.
    """
    # TODO: Fix this recursive import
    from .datastruct import TOC
    new_toc = TOC()
    for inm, fnm, typ in toc:
        if typ == 'EXTENSION':
            # In some rare cases extension might already contain suffix.
            # Skip it in this case.
            if not inm.endswith(EXTENSION_SUFFIXES[0]):
                # Use first suffix from the Python list of suffixes
                # for C extensions.
                inm = inm + EXTENSION_SUFFIXES[0]

        elif typ == 'DEPENDENCY':
            # Use the suffix from the filename.
            # TODO Verify what extensions are by DEPENDENCIES.
            binext = os.path.splitext(fnm)[1]
            if not os.path.splitext(inm)[1] == binext:
                inm = inm + binext
        new_toc.append((inm, fnm, typ))
    return new_toc


def checkCache(fnm, strip=False, upx=False, dist_nm=None):
    """
    Cache prevents preprocessing binary files again and again.

    'dist_nm'  Filename relative to dist directory. We need it on Mac
               to determine level of paths for @loader_path like
               '@loader_path/../../' for qt4 plugins.
    """
    from ..config import CONF
    # On darwin a cache is required anyway to keep the libaries
    # with relative install names. Caching on darwin does not work
    # since we need to modify binary headers to use relative paths
    # to dll depencies and starting with '@loader_path'.
    if not strip and not upx and not is_darwin and not is_win:
        return fnm

    if dist_nm is not None and ":" in dist_nm:
        # A file embedded in another pyinstaller build via multipackage
        # No actual file exists to process
        return fnm

    if strip:
        strip = True
    else:
        strip = False
    if upx:
        upx = True
    else:
        upx = False

    # Load cache index
    # Make cachedir per Python major/minor version.
    # This allows parallel building of executables with different
    # Python versions as one user.
    pyver = ('py%d%s') % (sys.version_info[0], sys.version_info[1])
    arch = platform.architecture()[0]
    cachedir = os.path.join(CONF['configdir'], 'bincache%d%d_%s_%s' % (strip, upx, pyver, arch))
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)
    cacheindexfn = os.path.join(cachedir, "index.dat")
    if os.path.exists(cacheindexfn):
        cache_index = load_py_data_struct(cacheindexfn)
    else:
        cache_index = {}

    # Verify if the file we're looking for is present in the cache.
    # Use the dist_mn if given to avoid different extension modules
    # sharing the same basename get corrupted.
    if dist_nm:
        basenm = os.path.normcase(dist_nm)
    else:
        basenm = os.path.normcase(os.path.basename(fnm))
    digest = cacheDigest(fnm)
    cachedfile = os.path.join(cachedir, basenm)
    cmd = None
    if basenm in cache_index:
        if digest != cache_index[basenm]:
            os.remove(cachedfile)
        else:
            # On Mac OS X we need relative paths to dll dependencies
            # starting with @executable_path
            if is_darwin:
                dylib.mac_set_relative_dylib_deps(cachedfile, dist_nm)
            return cachedfile

    # Change manifest and its deps to private assemblies
    if fnm.lower().endswith(".manifest"):
        manifest = winmanifest.Manifest()
        manifest.filename = fnm
        with open(fnm, "rb") as f:
            manifest.parse_string(f.read())
        if manifest.publicKeyToken:
            logger.info("Changing %s into private assembly", os.path.basename(fnm))
        manifest.publicKeyToken = None
        for dep in manifest.dependentAssemblies:
            # Exclude common-controls which is not bundled
            if dep.name != "Microsoft.Windows.Common-Controls":
                dep.publicKeyToken = None

        manifest.writeprettyxml(cachedfile)
        return cachedfile

    if upx:
        if strip:
            fnm = checkCache(fnm, strip=True, upx=False)
        bestopt = "--best"
        # FIXME: Linux builds of UPX do not seem to contain LZMA (they assert out)
        # A better configure-time check is due.
        if CONF["hasUPX"] >= (3,) and os.name == "nt":
            bestopt = "--lzma"

        upx_executable = "upx"
        if CONF.get('upx_dir'):
            upx_executable = os.path.join(CONF['upx_dir'], upx_executable)
        cmd = [upx_executable, bestopt, "-q", cachedfile]
    else:
        if strip:
            strip_options = []
            if is_darwin:
                # The default strip behaviour breaks some shared libraries
                # under Mac OSX.
                # -S = strip only debug symbols.
                strip_options = ["-S"]
            cmd = ["strip"] + strip_options + [cachedfile]

    if not os.path.exists(os.path.dirname(cachedfile)):
        os.makedirs(os.path.dirname(cachedfile))
    shutil.copy2(fnm, cachedfile)
    os.chmod(cachedfile, 0o755)

    if os.path.splitext(fnm.lower())[1] in (".pyd", ".dll"):
        # When shared assemblies are bundled into the app, they must be
        # transformed into private assemblies or else the assembly
        # loader will not search for them in the app folder. To support
        # this, all manifests in the app must be modified to point to
        # the private assembly.

        # Also, if python.exe has dependent assemblies, check for
        # embedded manifest of cached pyd file because we may need to
        # 'fix it' for pyinstaller
        try:
            res = winmanifest.GetManifestResources(os.path.abspath(cachedfile))
        except winresource.pywintypes.error as e:
            if e.args[0] == winresource.ERROR_BAD_EXE_FORMAT:
                # Not a win32 PE file
                pass
            else:
                logger.error(os.path.abspath(cachedfile))
                raise
        else:
            if winmanifest.RT_MANIFEST in res and len(res[winmanifest.RT_MANIFEST]):
                for name in res[winmanifest.RT_MANIFEST]:
                    for language in res[winmanifest.RT_MANIFEST][name]:
                        try:
                            manifest = winmanifest.Manifest()
                            manifest.filename = ":".join([cachedfile,
                                                          str(winmanifest.RT_MANIFEST),
                                                          str(name),
                                                          str(language)])
                            manifest.parse_string(res[winmanifest.RT_MANIFEST][name][language],
                                                  False)
                        except Exception as exc:
                            logger.error("Cannot parse manifest resource %s, "
                                         "%s from", name, language)
                            logger.error(cachedfile)
                            logger.exception(exc)
                        else:
                            # change manifest to private assembly
                            if manifest.publicKeyToken:
                                logger.info("Changing %s into a private assembly",
                                            os.path.basename(fnm))
                            manifest.publicKeyToken = None

                            # Fix the embedded manifest (if any):
                            # Extension modules built with Python 2.6.5 have
                            # an empty <dependency> element, we need to add
                            # dependentAssemblies from python.exe for
                            # pyinstaller.
                            _depNames = set([dep.name for dep in
                                             manifest.dependentAssemblies])
                            for pydep in CONF['pylib_assemblies']:
                                if not pydep.name in _depNames:
                                    logger.info("Adding %r to dependent "
                                                "assemblies of %r",
                                                pydep.name, cachedfile)
                                    manifest.dependentAssemblies.append(pydep)
                                    _depNames.update(pydep.name)

                            # Change dep to private assembly
                            for dep in manifest.dependentAssemblies:
                                # Exclude common-controls which is not bundled
                                if dep.name != "Microsoft.Windows.Common-Controls":
                                    dep.publicKeyToken = None
                            try:
                                manifest.update_resources(os.path.abspath(cachedfile),
                                                          [name],
                                                          [language])
                            except Exception as e:
                                logger.error(os.path.abspath(cachedfile))
                                raise

    if cmd:
        try:
            logger.info("Executing - " + ' '.join(cmd))
            compat.exec_command(*cmd)
        except OSError as e:
            raise SystemExit("Execution failed: %s" % e)

    # update cache index
    cache_index[basenm] = digest
    save_py_data_struct(cacheindexfn, cache_index)

    # On Mac OS X we need relative paths to dll dependencies
    # starting with @executable_path
    if is_darwin:
        dylib.mac_set_relative_dylib_deps(cachedfile, dist_nm)
    return cachedfile


def cacheDigest(fnm):
    data = open(fnm, "rb").read()
    digest = hashlib.md5(data).digest()
    return digest


def _check_path_overlap(path):
    """
    Check that path does not overlap with WORKPATH or SPECPATH (i.e.
    WORKPATH and SPECPATH may not start with path, which could be
    caused by a faulty hand-edited specfile)

    Raise SystemExit if there is overlap, return True otherwise
    """
    from ..config import CONF
    specerr = 0
    if CONF['workpath'].startswith(path):
        logger.error('Specfile error: The output path "%s" contains '
                     'WORKPATH (%s)', path, CONF['workpath'])
        specerr += 1
    if CONF['specpath'].startswith(path):
        logger.error('Specfile error: The output path "%s" contains '
                     'SPECPATH (%s)', path, CONF['specpath'])
        specerr += 1
    if specerr:
        raise SystemExit('Error: Please edit/recreate the specfile (%s) '
                         'and set a different output name (e.g. "dist").'
                         % CONF['spec'])
    return True


def _rmtree(path):
    """
    Remove directory and all its contents, but only after user confirmation,
    or if the -y option is set
    """
    from ..config import CONF
    if CONF['noconfirm']:
        choice = 'y'
    elif sys.stdout.isatty():
        choice = compat.stdin_input('WARNING: The output directory "%s" and ALL ITS '
                           'CONTENTS will be REMOVED! Continue? (y/n)' % path)
    else:
        raise SystemExit('Error: The output directory "%s" is not empty. '
                         'Please remove all its contents or use the '
                         '-y option (remove output directory without '
                         'confirmation).' % path)
    if choice.strip().lower() == 'y':
        logger.info('Removing dir %s', path)
        shutil.rmtree(path)
    else:
        raise SystemExit('User aborted')
