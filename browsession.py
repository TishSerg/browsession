#!/usr/bin/env python3
################################################################################
# Browser Session SafeKeeper
################################################################################
# Monitors and makes a backups of browser session.
# \file		    browsession.py
# \version 	    <see __version__>
# \date		    2020-11-21
# \author	    TishSerg (TishSerg@gmail.com) 
# \copyright    GNU GPL
################################################################################

__version__ = '0.2.0'

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
            'BrowserStateDetection': 'Chromium',
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
        },
        'ExtraFilesToBackup': { # Usually heavy files
        }
    }

    global config
    config = configparser.ConfigParser(allow_no_value=True, interpolation=None, empty_lines_in_values=False)
    config.optionxform = str    # Make option names case-sensitive
    config.read_dict(default_config)
    read_files = config.read(filenames)
    
    if not read_files:
        filename = filenames if isinstance(filenames, str) else filenames[0]
        with open(filename, mode='x',) as config_file:
            config.write(config_file)
        logging.critical(
            f"Config file wasn't found. A template config file '{filename}' has been created. " 
            "Adjust it to your needs (at least specify path to browser's profile and files to copy).")
        raise RuntimeError(f'Config file "{filename}" is not found.')

    if not config['Paths']['BrowserProfile']:
        logging.critical("Path to browser profile isn't specified in config!")
        raise RuntimeError("Path to browser profile isn't specified in config!")
    config['Paths']['BrowserProfile'] = os.path.normpath(os.path.expandvars(config['Paths']['BrowserProfile']))
    config['Paths']['BackupDirsRoot'] = os.path.normpath(os.path.expandvars(config['Paths']['BackupDirsRoot']))
    
    files_to_backup_valid_count = 0

    for opt_name, opt_value in config.items('MainFilesToBackup'):
        if opt_value and not config['MainFilesToBackup'].getboolean(opt_name):
            continue    # if file explicitly set to false - don't include it
        browser_profile_files.add(opt_name)
        full_path = os.path.join(config['Paths']['BrowserProfile'], opt_name)
        if os.path.exists(full_path):
            files_to_backup_valid_count += 1
    
    if files_to_backup_valid_count < 1:
        logging.critical(f"None main files/dirs found in {config['Paths']['BrowserProfile']}")
        raise RuntimeError(f"None main files/dirs found in {config['Paths']['BrowserProfile']}")
        
    for opt_name, opt_value in config.items('ExtraFilesToBackup'):
        if opt_value and not config['ExtraFilesToBackup'].getboolean(opt_name):
            continue    # if file explicitly set to false - don't include it
        browser_profile_extra_files.add(opt_name)

    logging.info(
        'Backup config: "{}" -> "{}"'.format(
            config['Paths']['BrowserProfile'], os.path.abspath(config['Paths']['BackupDirsRoot']))
        )
    

def check_chromium_is_running_win() -> bool:
    with os.scandir(os.path.join(config['Paths']['BrowserProfile'], 'Sessions')) as dir_entries:
        for dir_entry in dir_entries:
            if dir_entry.is_file():
                try:
                    with open(dir_entry.path, 'rb'):
                        pass
                except PermissionError:
                    return True # Any locked file indicates browser is running (Windows only)
    return False    # No locked files were encountered - browser isn't running (Windows only)

def check_chromium_is_running() -> bool:
    filepath = os.path.join(config['Paths']['BrowserProfile'], 'History-journal')
    if not os.path.exists(filepath):
        return False
    else:
        statinfo = os.stat(os.path.join(config['Paths']['BrowserProfile'], 'History-journal'))
        return True if statinfo.st_size > 0 else False

def check_firefox_is_running() -> bool:
    return not os.path.exists(os.path.join(config['Paths']['BrowserProfile'], 'sessionstore.jsonlz4'))

def check_opera_is_running_win() -> bool:
    return os.path.exists(os.path.join(config['Paths']['BrowserProfile'], 'lockfile'))  # Windows only

def check_opera_is_running() -> bool:
    with os.scandir(config['Paths']['BrowserProfile']) as dir_entries:
        for dir_entry in dir_entries:
            if dir_entry.is_file() and dir_entry.name.startswith('ssdfp') and dir_entry.name.endswith('.lock'):
                return True
    return False

def is_browser_running() -> bool:
    check_browser_is_running = {
        'Chromium-win'.casefold(): check_chromium_is_running_win,
        'Chromium'.casefold(): check_chromium_is_running,
        'Firefox'.casefold(): check_firefox_is_running,
        'Opera-win'.casefold(): check_opera_is_running_win,
        'Opera'.casefold(): check_opera_is_running,
    }

    return check_browser_is_running[config['Settings']['BrowserStateDetection'].casefold()]()


def copy_profile(destination_path: str, include_extra: bool = False):
    try:
        os.mkdir(destination_path)
    except FileExistsError:
        logging.error(f'"{destination_path}" already exist. Profile backuping skipped.')
        return

    files_to_copy = browser_profile_files.union(browser_profile_extra_files) if include_extra else browser_profile_files
    
    for filename in files_to_copy:
        source_path = os.path.join(config['Paths']['BrowserProfile'], filename)
        if os.path.isdir(source_path):
            dir_basename = os.path.basename(source_path.rstrip(os.sep+(os.altsep if os.altsep else '')))
            try:
                copy_path = shutil.copytree(
                    source_path, os.path.join(destination_path, dir_basename, ''),  # The '' is to add sep as dir indication
                    symlinks=True, ignore=shutil.ignore_patterns('*.tmp'), dirs_exist_ok=False)
            except OSError as errs:
                for err in errs.args[0]:
                    logging.warning(err[2])
        else:
            try:
                copy_path = shutil.copy2(source_path, destination_path)
            except PermissionError:
                logging.warning(f'No access to "{source_path}"')
            except FileNotFoundError:
                logging.warning(f'No such file or directory "{source_path}"')
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

def dircmp_count_diff_files(directory: filecmp.dircmp) -> int:
    diff_files_count = len(directory.diff_files)
    for subdir in directory.subdirs.values():
        diff_files_count += dircmp_count_diff_files(subdir)
    return diff_files_count

def check_profile_files_changed(backup_dir_path: str) -> bool:
    # filecmp.clear_cache() # Looks like unnecessary
    dir_cmp = filecmp.dircmp(config['Paths']['BrowserProfile'], backup_dir_path)

    if not dir_cmp.common:  # For case when backup_dir is empty (may be when backup drive ran out of free space)
        return True
    
    return dircmp_count_diff_files(dir_cmp) > 0 # Unreliable: if in backup_dir are only files that rarely change

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
    logging.info('Browser just launched.')

def browser_stop_handler():
    logging.info('Browser just shutdown. Making a backup...')
    make_backup(False)

async def emergency_watcher():
    while True:
        await asyncio.sleep(5)
        if is_browser_running():
            browser_profile_drive_usage = shutil.disk_usage(config['Paths']['BrowserProfile'])
            if browser_profile_drive_usage.free < eval(config['Settings']['EmergencyFreeSpaceTrigger']):
                logging.warning('Browser profile drive free space is running out! ({:.1f} MiB remaining) Making emergency backup...'.format(browser_profile_drive_usage.free / 1024 / 1024))
                make_backup(True)
                await asyncio.sleep(config['Settings'].getfloat('EmergencyFreeSpaceDelay')) # Rest after emergency backup


async def browser_state_watcher():
    browser_have_been_running = is_browser_running()
    while True:
        await asyncio.sleep(1)
        if is_browser_running():
            if not browser_have_been_running:
                browser_start_handler()
                browser_have_been_running = True
        else:
            if browser_have_been_running:
                browser_stop_handler()
                browser_have_been_running = False


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

    logging.info('Browsession v'+__version__+' is starting...')

    if os.getcwd().casefold() != sys.path[0].casefold() if os.name == 'nt' else os.getcwd() != sys.path[0]:
        logging.warning(f'Current dir ({os.getcwd()}) changed to script dir ({sys.path[0]})')
        os.chdir(sys.path[0])

    os.makedirs('logs', exist_ok=True)
    logfile_hdlr = logging.handlers.TimedRotatingFileHandler(
        'logs/everything.log', backupCount=5, encoding='utf-8', when='midnight', atTime=datetime.time(hour=4))
    logfile_fmt = logging.Formatter('[{asctime}] {levelname:8} {filename}:{lineno}:\t{message}', style='{')
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
    
    if is_browser_running():
        logging.info('Browser is running at Browsession startup. Backup is skipped.')
    else:
        logging.info('Browser is not running at Browsession startup. Making a backup...')
        make_backup(False)
    
    logging.info('Browsession is on duty.')

    await asyncio.gather(
        browser_state_watcher(),
        emergency_watcher()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('Browsession was stopped by user.')
