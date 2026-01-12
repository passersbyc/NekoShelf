from core.cli import MoeCLI
from core.utils import Colors

if __name__ == '__main__':
    try:
        MoeCLI().cmdloop()
    except KeyboardInterrupt:
        print(Colors.pink("\n萌萌去休息了喵~ 拜拜！"))
