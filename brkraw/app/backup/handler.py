import os
from brkraw.app.tonifti import StudyToNifti
from brkraw.api.config.utils.functools import get_dirsize, \
    get_filesize, yes_or_no, print_internal_error, TimeCounter
import sys
import datetime
import tqdm
import pickle
import zipfile
from .cache import BackupCache
import pickle
import getpass


_bar_fmt = '{l_bar}{bar:20}{r_bar}{bar:-20b}'
_user = getpass.getuser()
_width = 80
_line_sep_1 = '-' * _width
_line_sep_2 = '=' * _width
_empty_sep = ''

class BackupCacheHandler:
    def __init__(self, raw_path, backup_path, fname='.brk-backup_cache'):
        """ Handler class for backup data

        Args:
            raw_path:       path for raw dataset
            backup_path:    path for backup dataset
            fname:          file name to pickle cache data
        """
        self._cache = None
        self._rpath = os.path.expanduser(raw_path)
        self._apath = os.path.expanduser(backup_path)
        self._cache_path = os.path.join(self._apath, fname)
        self._load_pickle()
        # self._parse_info()

    def _load_pickle(self):
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, 'rb') as cache:
                    self._cache = pickle.load(cache)
            except EOFError:
                os.remove(self._cache_path)
                self._cache = BackupCache()
        else:
            self._cache = BackupCache()
        self._save_pickle()

    def _save_pickle(self):
        with open(self._cache_path, 'wb') as f:
            pickle.dump(self._cache, f)

    def logging(self, message, method):
        method = 'Handler.{}'.format(method)
        self._cache.logging(message, method)

    @property
    def is_duplicated(self):
        return self._cache.is_duplicated

    @property
    def get_rpath_obj(self):
        return self._cache.get_rpath_obj

    @property
    def get_bpath_obj(self):
        return self._cache.get_bpath_obj

    @property
    def arc_data(self):
        return self._cache.arc_data

    @property
    def raw_data(self):
        return self._cache.raw_data

    @property
    def scan(self):
        return self._parse_info

    def _parse_info(self):
        print('\n-- Parsing metadata from the raw and archived directories --')
        list_of_raw = sorted([d for d in os.listdir(self._rpath) if
                              os.path.isdir(os.path.join(self._rpath, d)) and 'import' not in d])
        list_of_brk = sorted([d for d in os.listdir(self._apath) if
                              (os.path.isfile(os.path.join(self._apath, d)) and
                               (d.endswith('zip') or d.endswith('PvDatasets')))])

        # parse dataset
        print('\nScanning raw datasets and update cache...')
        for r in tqdm.tqdm(list_of_raw, bar_format=_bar_fmt):
            self._cache.set_raw(r, raw_dir=self._rpath)
        self._save_pickle()

        print('\nScanning archived datasets and update cache...')
        for b in tqdm.tqdm(list_of_brk, bar_format=_bar_fmt):
            self._cache.set_arc(b, arc_dir=self._apath, raw_dir=self._rpath)
        self._save_pickle()

        # update raw dataset information (raw dataset cache will remain even its removed)
        print('\nScanning raw dataset cache...')
        for r in tqdm.tqdm(self.raw_data[:], bar_format=_bar_fmt):
            if r.path != None:
                if not os.path.exists(os.path.join(self._rpath, r.path)):
                    if not r.removed:
                        r.removed = True
        self._save_pickle()

        print('\nReviewing the cached information...')
        for b in tqdm.tqdm(self.arc_data[:], bar_format=_bar_fmt):
            arc_path = os.path.join(self._apath, b.path)
            if not os.path.exists(arc_path):  # backup dataset is not existing, remove the cache
                self.arc_data.remove(b)
            else:  # backup dataset is existing then check status again
                if b.issued:  # check if the issue has benn resolved.
                    if b.crashed:  # check if the dataset re-backed up.
                        if zipfile.is_zipfile(arc_path):
                            b.crashed = False  # backup success!
                            b.issued = False if self.is_same_as_raw(b.path) else True
                            if b.issued:
                                if b.garbage:
                                    if StudyToNifti(arc_path).is_pvdataset:
                                        b.garbage = False
                        # else the backup dataset it still crashed.
                    else:  # the dataset has an issue but not crashed, so check if the issue has been resolved.
                        b.issued = False if self.is_same_as_raw(b.path) else True
                        if not b.issued:  # if issue resolved
                            r = self.get_rpath_obj(b.path, by_arc=True)
                            r.backup = True
                else:  # if no issue with the dataset, do nothing.
                    r = self.get_rpath_obj(b.path, by_arc=True)
                    if not r.backup:
                        r.backup = True
        self._save_pickle()

    def is_same_as_raw(self, filename):
        arc = StudyToNifti(os.path.join(self._apath, filename))
        if arc.pvobj.path != None:
            raw_path = os.path.join(self._rpath, arc.pvobj.path)
            if os.path.exists(raw_path):
                raw = StudyToNifti(raw_path)
                return arc.num_recos == raw.num_recos
            else:
                return None
        else:
            return None

    def get_duplicated(self):
        duplicated = dict()
        for b in self.arc_data:
            if self.is_duplicated(b.path, by_arc=True):
                rpath = self.get_rpath_obj(b.path, by_arc=True).path
                if rpath in duplicated.keys():
                    duplicated[rpath].append(b.path)
                else:
                    duplicated[rpath] = [b.path]
            else:
                pass
        return duplicated

    def get_list_for_backup(self):
        return [r for r in self.get_incompleted() if not r.garbage]

    def get_issued(self):
        return [b for b in self.arc_data if b.issued]

    def get_crashed(self):
        return [b for b in self.arc_data if b.crashed]

    def get_incompleted(self):
        return [r for r in self.raw_data if not r.backup]

    def get_completed(self):
        return [r for r in self.raw_data if r.backup]

    def get_garbage(self):
        return [b for b in self.arc_data if b.garbage]

    @staticmethod
    def _gen_header(title, width=_width):
        lines = []
        gen_by = 'Generated by {}'.format(_user).rjust(width)

        lines.append(_empty_sep)
        lines.append(_line_sep_2)
        lines.append(_empty_sep)
        lines.append(title.center(width))
        lines.append(gen_by)
        lines.append(_line_sep_2)
        lines.append(_empty_sep)
        return lines

    def _get_backup_status(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = self._gen_header('Report of the status of archived data [{}]'.format(now))
        list_need_to_be_backup = self.get_list_for_backup()[:]
        total_list = len(list_need_to_be_backup)
        if len(list_need_to_be_backup):
            lines.append('>> The list of raw data need to be archived.')
            lines.append('[Note: The list exclude the raw data does not contain any binary file]')
            lines.append(_line_sep_1)
            lines.append('{}{}'.format('Rawdata Path'.center(_width-10), 'Size'.rjust(10)))
            for r in list_need_to_be_backup:
                if len(r.path) > _width-10:
                    path_name = '{}... '.format(r.path[:_width-14])
                else:
                    path_name = r.path
                raw_path = os.path.join(self._rpath, r.path)
                dir_size, unit = get_dirsize(raw_path)
                if unit == 'B':
                    dir_size = '{} {}'.format(dir_size, unit).rjust(10)
                else:
                    dir_size = '{0:.2f}{1}'.format(dir_size, unit).rjust(10)
                lines.append('{}{}'.format(path_name.ljust(_width-10), dir_size))
            lines.append(_line_sep_1)
            lines.append(_empty_sep)

        list_issued = self.get_issued()
        total_list += len(list_issued)
        if len(list_issued):
            lines.append('>> Failed or incompleted archived data.')
            lines.append('[Note: The listed data are either crashed or incompleted]')
            lines.append(_line_sep_1)
            lines.append('{}{}{}'.format('Archived Path'.center(60),
                                         'Condition'.rjust(10),
                                         'Size'.rjust(10)))
            for b in self.get_issued():
                if len(b.path) > _width-20:
                    path_name = '{}... '.format(b.path[:_width-24])
                else:
                    path_name = b.path
                arc_path = os.path.join(self._apath, b.path)
                file_size, unit = get_filesize(arc_path)
                if b.crashed:
                    raw_path = self.get_rpath_obj(b.path, by_arc=True).path
                    if raw_path is None:
                        condition = 'Failed'
                    else:
                        condition = 'Crashed'
                else:
                    condition = 'Issued'
                if unit == 'B':
                    file_size = '{} {}'.format(file_size, unit).rjust(10)
                else:
                    file_size = '{0:.2f}{1}'.format(file_size, unit).rjust(10)
                lines.append('{}{}{}'.format(path_name.ljust(_width-20),
                                             condition.center(10),
                                             file_size))
            lines.append(_line_sep_1)
            lines.append(_empty_sep)

        list_duplicated = self.get_duplicated()
        total_list += len(list_duplicated)
        if len(list_duplicated.keys()):
            lines.append('>> List of duplicated archived data.')
            lines.append('[Note: The listed raw data has been archived into multiple files]')
            lines.append(_line_sep_1)
            lines.append('{}  {}'.format('Raw Path'.center(int(_width/2)-1),
                                         'Archived'.center(int(_width/2)-1)))
            for rpath, bpaths in list_duplicated.items():
                if rpath is None:
                    rpath = '-- Removed --'
                if len(rpath) > int(_width/2)-1:
                    rpath = '{}... '.format(rpath[:int(_width/2)-5])
                for i, bpath in enumerate(bpaths):
                    if len(bpath) > int(_width/2)-1:
                        bpath = '{}... '.format(bpath[:int(_width/2)-5])
                    if i == 0:
                        lines.append('{}:-{}'.format(rpath.ljust(int(_width/2)-1),
                                                     bpath.ljust(int(_width/2)-1)))
                    else:
                        lines.append('{} -{}'.format(''.center(int(_width/2)-1),
                                                     bpath.ljust(int(_width/2)-1)))
            lines.append(_line_sep_1)
            lines.append(_empty_sep)

        if total_list == 0:
            lines.append(_empty_sep)
            lines.append('The status of archived data is up-to-date...'.center(80))
            lines.append(_empty_sep)
            lines.append(_line_sep_1)
        return '\n'.join(lines)

    def print_status(self, fobj=sys.stdout):
        summary = self._get_backup_status()
        print(summary, file=fobj)

    def print_completed(self, fobj=sys.stdout):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = self._gen_header('List of archived dataset [{}]'.format(now))
        list_of_completed = self.get_completed()
        if len(list_of_completed):
            lines.append(_line_sep_1)
            lines.append('{}{}{}'.format('Rawdata Path'.center(_width - 20),
                                         'Removed'.rjust(10),
                                         'Archived'.rjust(10)))
            for r in list_of_completed:
                if len(r.path) > _width - 20:
                    path_name = '{}... '.format(r.path[:_width - 24])
                else:
                    path_name = r.path
                removed = 'True' if r.removed else 'False'
                archived = 'True' if r.backup else 'False'
                lines.append('{}{}{}'.format(path_name.ljust(_width - 20),
                                             removed.center(10),
                                             archived.center(10)))
            lines.append(_line_sep_1)
            lines.append(_empty_sep)
        else:
            lines.append(_empty_sep)
            lines.append('No archived data...'.center(80))
            lines.append(_empty_sep)
            lines.append(_line_sep_1)
        summary = '\n'.join(lines)
        print(summary, file=fobj)

    def clean(self):
        print('\n[Warning] The archived data that contains any issue will be deleted by this command '
              'and it cannot be revert.')
        print('          Prior to run this, please update the cache for data status using "review" function.\n')
        ans = yes_or_no('Are you sure to continue?')

        if ans:
            list_data = dict(issued=self.get_issued()[:],
                             garbage=self.get_garbage()[:],
                             crashed=self.get_crashed()[:],
                             duplicated=self.get_duplicated().copy())
            for label, dset in list_data.items():
                if label == 'duplicated':
                    print('\nStart removing {} archived data...'.format(label.upper()))
                    if len(dset.items()):
                        for raw_dname, arcs in dset.items():
                            if raw_dname != None:
                                raw_path = os.path.join(self._rpath, raw_dname)
                                if os.path.exists(raw_path):
                                    r_size, r_unit = get_dirsize(raw_path)
                                    r_size = '{0:.2f} {1}'.format(r_size, r_unit)
                                else:
                                    r_size = 'Removed'
                                if len(raw_dname) < 60:
                                    raw_dname = '{}...'.format(raw_dname[:56])
                            else:
                                r_size = 'Removed'
                                raw_dname = 'No name'
                            print('Raw dataset: [{}] {}'.format(raw_dname.ljust(60), r_size.rjust(10)))
                            num_dup = len(arcs)
                            dup_list = ['  +-{}'] * num_dup
                            print('\n'.join(dup_list).format(*arcs))
                            for arc_fname in arcs:
                                path_to_clean = os.path.join(self._apath, arc_fname)
                                ans_4rm = yes_or_no(' - Are you sure to remove [{}] ?\n  '.format(arc_fname))
                                if ans_4rm:
                                    try:
                                        os.remove(path_to_clean)
                                        a = self.get_bpath_obj(arc_fname)
                                        if len(a):
                                            self.arc_data.remove(a[0])
                                    except OSError:
                                        error = NotImplementedError(path_to_clean)
                                        self.logging(error.message, 'clean')
                                        print('    Failed! The file is locked.')
                                    else:
                                        raise NotImplementedError
                else:
                    if len(dset):
                        print('\nStart removing {} archived data...'.format(label.upper()))

                        def ask_to_remove():
                            ans_4rm = yes_or_no(' - Are you sure to remove [{}] ?\n  '.format(path_to_clean))
                            if ans_4rm:
                                try:
                                    os.remove(path_to_clean)
                                    self.arc_data.remove(a)
                                except OSError:
                                    error = NotImplementedError(path_to_clean)
                                    self.logging(error.message, 'clean')
                                    print('    Failed! The file is locked.')
                                else:
                                    raise NotImplementedError
                        for a in dset:
                            path_to_clean = os.path.join(self._apath, a.path)
                            if label == 'issued':
                                if a.garbages or a.crashed:
                                    pass
                                else:
                                    ask_to_remove()
                            elif label == 'garbage':
                                if a.crashed:
                                    pass
                                else:
                                    ask_to_remove()
        self._save_pickle()

    def backup(self, fobj=sys.stdout):
        list_raws = self.get_list_for_backup()[:]
        list_issued = self.get_issued()[:]
        print('\nStarting backup for raw data not listed in the cache...')
        self.logging('Archiving process starts...', 'backup')

        for i, dlist in enumerate([list_raws, list_issued]):
            if i == 0:
                print('\n[step1] Archiving the raw data that has not been archived.')
                self.logging('Archive the raw data has not been archived...', 'backup')
            elif i == 1:
                print('\n[step2] Archiving the data that has issued on archived data.')
                self.logging('Archive the raw data contains any issue...', 'backup')

            for r in tqdm.tqdm(dlist, unit=' dataset(s)', bar_format=_bar_fmt):
                run_backup = True
                raw_path = os.path.join(self._rpath, r.path)
                arc_path = os.path.join(self._apath, '{}.zip'.format(r.path))
                tmp_path = os.path.join(self._apath, '{}.part'.format(r.path))
                if os.path.exists(raw_path):
                    if os.path.exists(tmp_path):
                        print(' -[{}] is detected and removed...'.format(tmp_path), file=fobj)
                        os.unlink(tmp_path)
                    if os.path.exists(arc_path):
                        if not zipfile.is_zipfile(arc_path):
                            print(' -[{}] is crashed file, removing...'.format(arc_path), file=fobj)
                            os.unlink(arc_path)
                        else:
                            arc = StudyToNifti(arc_path)
                            raw = StudyToNifti(raw_path)
                            if arc.is_pvdataset:
                                if arc.num_recos != raw.num_recos:
                                    print(' - [{}] is mismatching with the corresponding raw data, '
                                          'removing...'.format(arc_path), file=fobj)
                                    os.unlink(arc_path)
                                else:
                                    run_backup = False
                            else:
                                print(' - [{}] is mismatching with the corresponding raw data, '
                                      'removing...'.format(arc_path), file=fobj)
                                os.unlink(arc_path)
                    if run_backup:
                        print('\n :: Compressing [{}]...'.format(raw_path), file=fobj)
                        # Compressing
                        timer = TimeCounter()
                        try:  # exception handling in case compression is failed
                            with zipfile.ZipFile(tmp_path, 'w') as zip:
                                # prepare file counters for use of tqdm
                                file_counter = 0
                                for _ in os.walk(raw_path):
                                    file_counter += 1

                                for i, (root, dirs, files) in tqdm.tqdm(enumerate(os.walk(raw_path)),
                                                                        bar_format=_bar_fmt,
                                                                        total=file_counter,
                                                                        unit=' file(s)'):
                                    splitted_root = root.split(os.sep)
                                    if i == 0:
                                        root_idx = splitted_root.index(r.path)
                                    for f in files:
                                        arc_name = os.sep.join(splitted_root[root_idx:] + [f])
                                        zip.write(os.path.join(root, f), arcname=arc_name)
                            print(' - [{}] is created.'.format(os.path.basename(arc_path)), file=fobj)

                        except Exception:
                            print_internal_error(fobj)
                            error = NotImplementedError(raw_path)
                            self.logging(error.message, 'backup')
                            raise error

                        print(' - processed time: {} sec'.format(timer.time()), file=fobj)

                        # Backup validation
                        if not os.path.exists(tmp_path):  # Check if the file is generated
                            error = NotImplementedError(raw_path)
                            self.logging(error.message, 'backup')
                            raise error
                        else:
                            try:
                                os.rename(tmp_path, arc_path)
                            except:
                                print_internal_error(fobj)
                                raise NotImplementedError