################################################################################
# Browser Session SafeKeeper
################################################################################
# Monitors and makes a backups of browser session.
# \file		browsession.py
# \version 	<see __version__>
# \date		2020-09-14
# \author	TishSerg (TishSerg@gmail.com) 
################################################################################

__version__ = '0.1.1'

import asyncio
import configparser
import datetime
import filecmp
import logging, logging.handlers
import os
import sys
import shutil
import time
from typing import Union, Iterable


config = None
browser_profile_files = set()
browser_profile_extra_files = set()

def load_config(filenames: Union[str, Iterable]):
    default_config = {
        'Paths': {
            'BrowserProfile': None,
            'BackupDirsRoot': 'BrowsessionBackups'
        },
        'Settings': {
            'BackupDirDatetimeFormat': '%Y-%m-%d %H-%M-%S',
            'FullBackupTag': 'regular',
            'EmergencyBackupTag': 'emergency',
            'EmergencyFreeSpaceTrigger': '1*1024*1024*1024',
            'EmergencyFreeSpaceDelay': '30',
            'FullBackupsStoreLimit': '5',
            'EmergencyBackupsStoreLimit': '3',
            'NoncompressedFullBackupsLimit': '1',
            'NoncompressedBackupsLimit': '1'
        },
        'MainFilesToBackup': {
            'Last Tabs': None,
            'Preferences': None,
            'Current Tabs': None,
            'Local State': None,
            'Bookmarks': None,
            'Last Session': None,
            'Current Session': None
        },
        'ExtraFilesToBackup': { # Usually heavy files
            'History': None,
            'BookmarksExtras': None,
            'Favicons': None,
            'Cookies': None
        }
    }

    global config
    config = configparser.ConfigParser(allow_no_value=True, interpolation=None, empty_lines_in_values=False)
    config.read_dict(default_config)
    read_files = config.read(filenames)
    
    if not read_files:
        filename = filenames if isinstance(filenames, str) else filenames[0]
        with open(filename, mode='x',) as config_file:
            config.write(config_file)
        logging.critical(
            f"Config file wasn't found. A template config file '{filename}' has been created. " 
            "Adjust it to your needs (at least specify path to browser's profile).")
        raise RuntimeError(f'Config file "{filename}" is not found.')

    if not config['Paths']['BrowserProfile']:
        logging.critical("Path to browser profile isn't specified in config!")
        raise RuntimeError("Path to browser profile isn't specified in config!")
    config['Paths']['BrowserProfile'] = os.path.normpath(os.path.expandvars(config['Paths']['BrowserProfile']))
    config['Paths']['BackupDirsRoot'] = os.path.normpath(os.path.expandvars(config['Paths']['BackupDirsRoot']))
    
    for opt_name, opt_value in config.items('MainFilesToBackup'):
        if opt_value and not config['MainFilesToBackup'].getboolean(opt_name):
            continue    # if file explicitly set to false - don't include it
        browser_profile_files.add(opt_name)
        full_path = os.path.join(config['Paths']['BrowserProfile'], opt_name)
        if not os.path.exists(full_path):
            logging.critical(f'In the browser profile main file "{opt_name}" is not found! ({full_path})')
            raise RuntimeError(f'In the browser profile main file "{opt_name}" is not found! ({full_path})')
        
    for opt_name, opt_value in config.items('ExtraFilesToBackup'):
        if opt_value and not config['ExtraFilesToBackup'].getboolean(opt_name):
            continue    # if file explicitly set to false - don't include it
        browser_profile_extra_files.add(opt_name)
    

def check_opera_running() -> bool:
    return os.path.exists(os.path.join(config['Paths']['BrowserProfile'], 'lockfile')) # Simple/Naive test
    # session_file = os.path.join(config['Paths']['BrowserProfile'], 'Current Session')
    # if not os.path.exists(session_file):
    #     raise Exception(f'Browser Session file not found: {session_file}')
    # try:
    #     with open(src, 'rb') as fsrc:
    #         pass
    # except PermissionError:
    #     return True
    # else:
    #     return False
    
def copy_profile(destination_path: str, include_extra: bool = False):
    try:
        os.mkdir(destination_path)
    except FileExistsError:
        logging.error(f'"{destination_path}" already exist. Profile backuping skipped.')
        return

    files_to_copy = browser_profile_files.union(browser_profile_extra_files) if include_extra else browser_profile_files
    
    for filename in files_to_copy:
        file_path = os.path.join(config['Paths']['BrowserProfile'], filename)
        try:
            copy_path = shutil.copy2(file_path, destination_path)
        except PermissionError:
            logging.warning(f'No access to "{file_path}"')
        else:
            logging.debug(f'Copied "{copy_path}"')

    logging.info(f'Profile copied: "{destination_path}"')
    
def get_latest_backup_dir(exclude_emergency: bool = True) -> os.DirEntry:
    with os.scandir(config['Paths']['BackupDirsRoot']) as bkp_entries:
        return max(
            (entry for entry in bkp_entries if 
                entry.is_dir() and 
                (config['Settings']['EmergencyBackupTag'] not in entry.name if exclude_emergency else True)), 
            key=lambda entry: entry.stat().st_ctime, default=None)

def archive(entry: os.DirEntry):
    logging.info(f'Archiving "{entry.name}"...')
    ar_path = shutil.make_archive(entry.path, 'zip', entry.path)
    logging.info(f'Archiving done: "{ar_path}"')
    orig_time = os.path.getctime(entry.path)
    os.utime(ar_path, times=(orig_time, orig_time)) # To still have correct sorting after dir => ar
    logging.info(f'Removing uncompressed "{entry.name}"...')
    shutil.rmtree(entry.path)
    logging.info(f'Removing "{entry.name}" done.')

def compress_backups(skip_latest_full_count: int = 1, skip_latest_emergency_count: int = 1):
    skipped_latest_full_count = 0
    skipped_latest_emergency_count = 0
    with os.scandir(config['Paths']['BackupDirsRoot']) as bkp_entries:
        bkp_dirs = (entry for entry in bkp_entries if  entry.is_dir())
        bkp_dirs = sorted(bkp_dirs, key=lambda entry: entry.stat().st_ctime, reverse=True)
        for entry in bkp_dirs:  # Due to reverse sorting, we will start with the latest
            if config['Settings']['EmergencyBackupTag'] in entry.name:
                if skipped_latest_emergency_count < skip_latest_emergency_count:
                    skipped_latest_emergency_count += 1
                    continue
                else:
                    archive(entry)
            else:   # Non-emergency backup
                if skipped_latest_full_count < skip_latest_full_count:
                    skipped_latest_full_count += 1
                    continue
                else:
                    archive(entry)

def remove(entry: os.DirEntry):
    logging.info(f'Removing old backup: {entry.name}')
    if entry.is_dir():
        shutil.rmtree(entry.path)
    else:
        os.remove(entry.path)

def remove_old_backups(skip_latest_full_count: int = 3, skip_latest_emergency_limit: int = 3):
    skipped_latest_full_count = 0
    skipped_latest_emergency_count = 0
    with os.scandir(config['Paths']['BackupDirsRoot']) as bkp_entries:
        bkp_entries = sorted(bkp_entries, key=lambda entry: entry.stat().st_mtime, reverse=True)
        for entry in bkp_entries:  # Due to reverse sorting, we will start with the latest
            if skipped_latest_full_count < skip_latest_full_count:
                if config['Settings']['EmergencyBackupTag'] in entry.name:
                    if skipped_latest_emergency_count < skip_latest_emergency_limit:
                        skipped_latest_emergency_count += 1
                        continue
                    else:
                        remove(entry)
                else:   # Non-emergency backup
                    skipped_latest_full_count += 1
                    continue
            else:
                remove(entry)
            
def check_profile_files_changed(backup_dir_path: str):
    # filecmp.clear_cache()
    match, mismatch, error = filecmp.cmpfiles(
        config['Paths']['BrowserProfile'], 
        backup_dir_path,
        browser_profile_files.union(browser_profile_extra_files))
    return len(mismatch) != 0 or len(match) == 0    # len(match) == 0 is here for case when backup_dir is empty (may be when backup drive ran out of free space)

def make_backup(emergency: bool):
    backup_tag = config['Settings']['EmergencyBackupTag'] if emergency else config['Settings']['FullBackupTag']

    existing_backup = get_latest_backup_dir(exclude_emergency=False if emergency else True)
    if existing_backup:
        if not check_profile_files_changed(existing_backup.path):
            logging.info(f'Profile files are not changed since "{existing_backup.name}". Skipping {backup_tag} backup.')
            return

    backup_dir_name = '{} ({})'.format(
        datetime.datetime.now().strftime(config['Settings']['BackupDirDatetimeFormat']), 
        backup_tag)
    backup_dir_path = os.path.join(config['Paths']['BackupDirsRoot'], backup_dir_name)
    copy_profile(backup_dir_path, include_extra=False if emergency else True)

    if not emergency:
        compress_backups(
            config['Settings'].getint('NoncompressedFullBackupsLimit'), 
            config['Settings'].getint('NoncompressedBackupsLimit'))
        remove_old_backups(
            config['Settings'].getint('FullBackupsStoreLimit'), 
            config['Settings'].getint('EmergencyBackupsStoreLimit'))

def browser_start_handler():
    logging.info('Opera just launched.')

def browser_stop_handler():
    logging.info('Opera just shutdown. Making a backup...')
    make_backup(False)

async def emergency_watcher():
    while True:
        await asyncio.sleep(5)
        if check_opera_running():
            browser_profile_drive_usage = shutil.disk_usage(config['Paths']['BrowserProfile'])
            if browser_profile_drive_usage.free < eval(config['Settings']['EmergencyFreeSpaceTrigger']):
                logging.warning('Browser profile drive free space is running out! ({:.1f} MiB remaining) Making emergency backup...'.format(browser_profile_drive_usage.free / 1024 / 1024))
                make_backup(True)
                await asyncio.sleep(config['Settings'].getfloat('EmergencyFreeSpaceDelay')) # Rest after emergency backup


async def browser_state_watcher():
    opera_have_been_running = check_opera_running()
    while True:
        await asyncio.sleep(1)
        if check_opera_running():
            if not opera_have_been_running:
                browser_start_handler()
                opera_have_been_running = True
        else:
            if opera_have_been_running:
                browser_stop_handler()
                opera_have_been_running = False


async def main():
    # logging.basicConfig(
    #     format='[%(asctime)s] %(levelname)-8s %(name)s @ %(funcName)s: %(message)s',
    #     level=logging.DEBUG)
    logging.getLogger().setLevel(logging.NOTSET)

    console_hdlr = logging.StreamHandler()
    console_hdlr.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)-8s %(message)s'))
    console_hdlr.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_hdlr)

    buffer_hdlr = logging.handlers.MemoryHandler(10, logging.CRITICAL)
    logging.getLogger().addHandler(buffer_hdlr)

    if os.getcwd().casefold() != sys.path[0].casefold() if os.name == 'nt' else os.getcwd() != sys.path[0]:
        logging.warning(f'Current dir ({os.getcwd()}) changed to script dir ({sys.path[0]})')
        os.chdir(sys.path[0])

    os.makedirs('logs', exist_ok=True)
    logfile_hdlr = logging.handlers.TimedRotatingFileHandler(
        'logs/everything.log', backupCount=5, encoding='utf-8', when='midnight', atTime=datetime.time(hour=4))
    logfile_fmt = logging.Formatter('[{asctime}] {levelname:8} {filename}:{lineno}: {message}', style='{')
    logfile_hdlr.setFormatter(logfile_fmt)
    logging.getLogger().addHandler(logfile_hdlr)

    # As soon as file logfile_hdlr start to work - flush accumulated log entries to it (if any) and get out.
    buffer_hdlr.setTarget(logfile_hdlr)
    buffer_hdlr.close()
    logging.getLogger().removeHandler(buffer_hdlr)
    
    try:
        load_config('browsession.ini')
    except RuntimeError:
        logging.critical('Exiting due to misconfiguration.')
        return

    os.makedirs(config['Paths']['BackupDirsRoot'], exist_ok=True)
    
    if check_opera_running():
        logging.info('Opera is running at Browsession startup. Backup is skipped.')
    else:
        logging.info('Opera is not running at Browsession startup. Making a backup...')
        make_backup(False)
    
    await asyncio.gather(
        browser_state_watcher(),
        emergency_watcher()
    )

if __name__ == "__main__":
    asyncio.run(main())
