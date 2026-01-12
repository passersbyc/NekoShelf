from core.cli import MoeCLI
from core.utils import Colors

def main():
    try:
        MoeCLI().cmdloop()
    except KeyboardInterrupt:
        print(Colors.pink("\n萌萌去休息了喵~ 拜拜！"))

if __name__ == '__main__':
    main()
