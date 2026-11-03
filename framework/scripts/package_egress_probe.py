from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED


def main():
    directory=Path(__file__).resolve().parents[1]/'tools/local_proxy'
    with ZipFile(directory/'egress-probe.jar','w',ZIP_DEFLATED) as archive:
        archive.write(directory/'build/dex/classes.dex','classes.dex')


if __name__=='__main__':
    main()
