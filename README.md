Browser Session SafeKeeper
==========================

This project is intended to keep your browser session safe.

It monitors and backups the session files so in case of disaster (eg. running out of free space on `AppData` drive, browser crash, etc) that led to losing the browser's session (eg. open tabs) you can copy the most recent version of your session from backup and get your hundreds of tabs back.

Just make Browsession run in the background on logon (eg. using [NSSM](https://nssm.cc/) or whatever way you prefer) and stop worrying about your tabs.

Also, Browsession can handle multiple browsers simultaneously. Just make a copy of Browsession dir with `browsession.ini` configured for a different browser and run its separate instance.

Quick start
-----------

Set `BrowserProfile` option in `browsession.ini` to your browser's profile dir path. You can find-out that by visiting a special page in your browser:

- Chromium-based: `about://version/`
- Firefox: `about:profiles`
- Opera: `opera://about/` (yeah it's also "Chromium-based", but heavily injured by devs)

Prepare dir where browser session backups will be stored. Set its path as the value of `BackupDirsRoot` option in `browsession.ini`. Highly recommended `BackupDirsRoot` to be _not_ on the volume where the browser's profile resides).

Set `BrowserStateDetection` option in `browsession.ini` as appropriate for your browser type.

Adjust files to backup in `[MainFilesToBackup]` and `[ExtraFilesToBackup]` sections.

You can find some config examples in files named `browsession-*-example.ini` or even use one of them as a template.

It's test time: Run Browsession and open/close your browser a few times to see Browsession's logs. 
If everything works fine - the next step is to make Browsession run in the background on logon.
