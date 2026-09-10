# android-tv-debloater

Remove selected Android TV applications through ADB for user `0`. The shared engine is written in POSIX sh, with device settings and package lists stored in separate profiles.

Before removing packages, the engine checks the device against the profile, restores the stock launcher if needed, and verifies that it is installed and enabled. The script does not configure Projectivy or select the HOME application.

## Structure

```text
debloater                                  # shared POSIX sh engine
profiles/xiaomi-mi-box-s-mdz-22-ab.conf      # Xiaomi profile
tests/test_debloater.py                     # tests with a fake ADB
```

## Prerequisites

The host needs `adb`, a POSIX-compatible `/bin/sh`, `grep`, and `tr`. Python 3 and ShellCheck are only needed for development checks.

Enable debugging on Android TV, connect the device through ADB, and authorize the connection on the TV screen. Check the connection:

```sh
adb devices
```

The selected device must have the `device` status. If several devices are connected, select one for all subsequent commands in the current terminal:

```sh
export ANDROID_SERIAL='serial-from-adb-devices'
adb get-state
```

The script does not accept `-s` or other ADB arguments: device selection uses the ADB environment. An ambiguous selection stops the script at the connection check.

## Usage

From the repository root:

```sh
./debloater profiles/xiaomi-mi-box-s-mdz-22-ab.conf
```

The only argument is a profile path, either absolute or relative to the current directory. Before running the script, review `REMOVE_PACKAGES` and remove any applications you want to keep from the list. Running the script applies changes immediately; there is no dry-run mode or interactive confirmation.

Packages are removed with:

```sh
adb shell pm uninstall --user 0 PACKAGE
```

This removes packages for user `0` without modifying the system image. The script does not pass `-k`, so it does not request preservation of application data.

## Execution order

1. Load the profile, validate required values, and ensure that the stock launcher is not in the removal list.
2. Check that `adb` is available and the device is connected.
3. Read manufacturer, model, and device. All three values must match the profile exactly. A read failure or mismatch stops execution before the engine issues any modifying commands.
4. If the stock launcher is missing for user `0`, restore it with `cmd package install-existing --user 0` and verify installation.
5. Enable the launcher with `pm enable --user 0` if needed and verify that it is enabled. If restoration or enabling fails, package removal does not start.
6. Remove packages from `REMOVE_PACKAGES`, checking that each is absent after the command. Packages that are already absent are skipped.
7. Print the package states and stock launcher state.

A package-state query failure stops the script immediately. If an individual uninstall fails, the script continues processing the list but exits with an error. Completed operations are not rolled back automatically.

Running the script again skips packages that have already been removed and does not restore them. It still checks the device and ensures that the stock launcher is available.

## Xiaomi profile

File: `profiles/xiaomi-mi-box-s-mdz-22-ab.conf`.

| ADB property | Expected value |
| --- | --- |
| `ro.product.manufacturer` | `Xiaomi` |
| `ro.product.model` | `MIBOX4` |
| `ro.product.device` | `oneday` |

Stock launcher: `com.google.android.tvlauncher`. The filename is a convenience; the device is checked against the three properties, not the profile name. The firmware version is not checked.

Current removal list:

```text
com.xiaomi.android.tvsetup.partnercustomizer
com.mitv.tvhome.atv
com.mitv.tvhome.mitvplus
com.mitv.tvhome.michannel
com.xiaomi.mitv.updateservice
com.miui.tv.analytics
com.xiaomi.statistic
com.mitv.milinkservice
com.amazon.amazonvideo.livingroom
com.netflix.ninja
com.google.android.videos
com.google.android.play.games
com.google.android.tvrecommendations
com.android.printspooler
com.mitv.dream
```

The list includes Netflix, Amazon Video, and the Xiaomi update service. It is not automatically tailored to the installed applications or firmware.

## Creating a profile

First, read the target device identifiers:

```sh
adb shell getprop ro.product.manufacturer
adb shell getprop ro.product.model
adb shell getprop ro.product.device
```

Create a file in `profiles/` with the exact values, the stock launcher package, and the packages to remove:

```sh
DEVICE_MANUFACTURER='exact manufacturer value'
DEVICE_MODEL='exact model value'
DEVICE_DEVICE='exact device value'

STOCK_LAUNCHER='package.of.stock.launcher'

REMOVE_PACKAGES='
package.to.remove
another.package.to.remove
'
```

All five variables are required and must be nonempty. In `REMOVE_PACKAGES`, use exact package names separated by spaces or newlines; place comments outside the quoted list. The stock launcher must not appear in this list. The engine fixes the target user at `USER_ID=0`.

Profiles are sourced with the shell `.` command and are trusted executable code. Use only configuration assignments: arbitrary profile commands would execute before the fingerprint check. This check prevents applying an ordinary profile to the wrong device; it does not isolate profile code.

## Output and errors

| Label | Meaning |
| --- | --- |
| `DEVICE` | The device matched the profile |
| `RESTORE`, `ENABLE`, `REMOVE` | The operation is starting; this does not yet confirm success |
| `REMOVED` | The package is absent for user `0`, including when it was absent before the run |
| `PRESENT` | The package remains installed for user `0` |
| `ENABLED` | The launcher is installed and enabled |
| `DISABLED`, `MISSING` | The final query found the launcher disabled or missing |
| `ERROR` | An error occurred; see the message for details |

Exit code `0` means execution completed without recorded operation errors, `1` indicates an explicit engine or uninstall error, and `2` indicates an incorrect argument count. Profile loading or variable validation failures also return a nonzero code determined by the shell. The final launcher report is informational: a state change found there does not itself change the exit code. External changes on the device are not blocked.

For `wrong manufacturer/model/device`, check the selected device and profile. For `cannot query package state`, restore the ADB connection and run the script again. If the launcher is also absent from the packages available for restoration, `install-existing` cannot restore it: the script does not download or install APK files.

## Restoring a package manually

If a package remains available in the system, restore it for user `0`:

```sh
adb shell cmd package install-existing --user 0 com.netflix.ninja
adb shell pm enable --user 0 com.netflix.ninja
adb shell pm list packages -e --user 0 com.netflix.ninja
```

Replace `com.netflix.ninja` with the desired package name and check the command results. This restores access to an existing package, not deleted application data. Remove it from `REMOVE_PACKAGES` to keep it on subsequent runs. The engine has no separate command to restore all packages.

## Development checks

From the repository root:

```sh
python3 -m unittest discover -s tests -v
sh -n debloater
shellcheck debloater
```

Tests use a fake `adb` and do not access a device. They cover fingerprint matching, stopping on query failures, restoring and enabling the launcher before removal, protecting the launcher from removal, failed operations, CRLF responses, and skipping packages that are already absent. They do not replace testing on real firmware.
