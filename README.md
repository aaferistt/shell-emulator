### Вариант №2

### О командах и содержимое
`--vfs-zip` - путь к архиву с VFS.
`--startup` - путь к стартовому скрипту.
Скрипты `start_ok.script` и `start_error.script`.
Файлы `*.b64` автоматически декодируются из base64.
`vfs_minimal.zip` (простая структура).
`vfs_deep.zip` (глубокая структура, >= 3 уровней).
Скрипт `start_deep.script`.
`ls` - содержимое папки.
`cd` - смена текущего каталога.
`history` - история команд.
`tree` - вывод структуры папок.
`chmod` - смена прав доступа.
`mv` - перемещение или переименование файлов/папок.
`pwd` — показать текущий путь.
`.bat`-файлы для запуска в отдельном окне.


### Запустить с минимальным VFS и скриптом
python sh_emulator.py --vfs-zip vfs_minimal.zip --startup start_ok.script

### Запустить с глубоким VFS
python sh_emulator.py --vfs-zip vfs_deep.zip --startup start_deep.script

### Запустить с ошибочным скриптом для демонстрации ошибок
python sh_emulator.py --vfs-zip vfs_minimal.zip --startup start_error.script

### Запуск в интерактивном режиме (REPL)
python sh_emulator.py --vfs-zip vfs_minimal.zip


### Клонировать репозиторий
```bash
git clone https://github.com/aaferistt/shell-emulator.git
cd shell-emulator
