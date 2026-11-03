# PROPIEDAD INTELECTUAL - AGX FRAMEWORK | AUTOMATIZACIÓN DE COMPILACIÓN Y DESPLIEGUE MÓVIL
"""Compilar, alinear, firmar y auditar el helper Java. No instala ni activa VPN."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts.helper_native import preparar_bibliotecas, verificar_bibliotecas_apk


def calcular_hash_apk(file_path):
    digest=hashlib.sha256()
    with Path(file_path).open('rb') as source:
        for block in iter(lambda:source.read(65536),b''):
            digest.update(block)
    return digest.hexdigest()


def localizar_sdk(explicit=None):
    candidates=[explicit,os.getenv('ANDROID_SDK_ROOT'),os.getenv('ANDROID_HOME')]
    config=ROOT/'config/native_dependencies.local.json'
    if config.is_file():
        candidates.append(Path(json.loads(config.read_text(encoding='utf-8'))['adb_path']).parents[1])
    candidates.append(ROOT.parent/'AGX/.tools/android-sdk')
    for candidate in candidates:
        if candidate and (Path(candidate)/'platforms').is_dir() and (Path(candidate)/'build-tools').is_dir():
            return Path(candidate).resolve()
    raise FileNotFoundError('Configurar ANDROID_SDK_ROOT o --sdk con SDK Android completo')


def herramientas(sdk):
    version=lambda p:tuple(map(int,re.findall(r'\d+',p.name)))
    platforms=sorted((p for p in (sdk/'platforms').iterdir() if (p/'android.jar').is_file()),key=version)
    builds=sorted((p for p in (sdk/'build-tools').iterdir() if (p/'lib/d8.jar').is_file()),key=version)
    if not platforms or not builds:
        raise FileNotFoundError('Faltan platforms/android.jar o build-tools/d8.jar')
    build=builds[-1]
    java_home=Path(os.environ['JAVA_HOME'])/'bin' if os.getenv('JAVA_HOME') else None
    def tool(name):
        executable=java_home/(name+('.exe' if os.name=='nt' else '')) if java_home else None
        found=str(executable) if executable and executable.is_file() else shutil.which(name)
        if not found:
            raise FileNotFoundError('Falta herramienta JDK: '+name)
        return found
    return build,platforms[-1]/'android.jar',{name:tool(name) for name in ('java','javac','keytool')}


def ejecutar(command,*,environment=None,timeout=120):
    result=subprocess.run(list(map(str,command)),cwd=ROOT,env=environment,check=True,timeout=timeout,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
        **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
    return result.stdout+result.stderr


def clave_local(keytool):
    folder=Path(os.getenv('LOCALAPPDATA') or Path.home()/'.local/share')/'AGXFramework/signing'
    folder.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        owner=ejecutar(['whoami']).strip()
        ejecutar(['icacls',folder,'/inheritance:r','/grant:r',owner+':(OI)(CI)F',
            '*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'])
    else:
        folder.chmod(0o700)
    credentials=folder/'lab-signing.json'
    key=folder/'agx-lab.p12'
    if not credentials.exists():
        if key.exists():
            raise RuntimeError('Existe keystore sin credenciales; no se sobrescribirá')
        fd=os.open(credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as file:
            json.dump({'password':secrets.token_urlsafe(32)},file)
    password=json.loads(credentials.read_text(encoding='utf-8'))['password']
    environment=os.environ.copy();environment['AGX_KEYSTORE_PASS']=password
    if not key.exists():
        ejecutar([keytool,'-genkeypair','-keystore',key,'-storetype','PKCS12','-alias','agx-lab',
            '-keyalg','RSA','-keysize','3072','-validity','3650','-dname','CN=AGX Laboratory',
            '-storepass:env','AGX_KEYSTORE_PASS','-keypass:env','AGX_KEYSTORE_PASS'],environment=environment)
    return key,environment


def verificar_y_registrar_helper(apk_destino=None,run_reporte=None,*,sdk=None):
    from core.audit_artifacts import reporte_bloqueado
    apk=Path(apk_destino or ROOT/'tools/agx_vpn_helper.apk')
    if not apk.is_file() or not apk.stat().st_size:
        raise FileNotFoundError('APK ausente o vacío')
    with zipfile.ZipFile(apk) as package:
        native_libraries=verificar_bibliotecas_apk(package)
        if not {'classes.dex','AndroidManifest.xml'}.issubset(package.namelist()):
            raise ValueError('APK sin DEX o manifiesto compilado')
        if not package.read('classes.dex').startswith(b'dex\n') or not package.read('AndroidManifest.xml').startswith(b'\x03\x00'):
            raise ValueError('DEX o manifiesto binario inválido')
    build,android_jar,jdk=herramientas(localizar_sdk(sdk))
    signing=ejecutar([jdk['java'],'-jar',build/'lib/apksigner.jar','verify','--verbose','--print-certs',apk])
    badging=ejecutar([build/('aapt.exe' if os.name=='nt' else 'aapt'),'dump','badging',apk])
    if "package: name='org.agx.vpntunnel'" not in badging:
        raise ValueError('Identidad de paquete APK no coincide')
    fingerprint=re.search(r'certificate SHA-256 digest:\s*([0-9a-fA-F]+)',signing)
    if not fingerprint or len(fingerprint.group(1))!=64:
        raise ValueError('No se obtuvo la huella SHA-256 del certificado de firma')
    digest=calcular_hash_apk(apk)
    info={'path':str(apk.resolve()),'size_bytes':apk.stat().st_size,'signature_verified':True,
          'certificate_sha256':fingerprint.group(1) if fingerprint else None,
          'package':'org.agx.vpntunnel','build_profile':'control_plane_only',
          'tcp_engine_included':False,'network_isolation_verified':False,'deployed':False}
    info['native_libraries']=native_libraries
    info['native_libraries_included']=bool(native_libraries)
    if native_libraries:
        info['build_profile']='native_libraries_pending_jni_integration'
    report=Path(run_reporte or ROOT/'runs/resultado_global.json')
    with reporte_bloqueado(report) as data:
        data['helper_apk_hash']=digest
        data['helper_apk_info']=info
        data['motor_tcp_android_deployment_ready']=False
    with reporte_bloqueado(apk.with_suffix('.build.json')) as data:
        data.update(info,helper_apk_hash=digest)
    print('[AGX-BUILD] APK firmado y estructura verificados. SHA-256: '+digest)
    print('[AGX-BUILD] Reporte: '+str(report.resolve()))
    print('[AGX-BUILD] Motor TCP no incluido; aislamiento de red sin acreditar.')
    return info


def compilar(sdk=None,output=None,report=None,native_manifest=None,require_native=False):
    if require_native and not native_manifest:
        raise ValueError('--require-native requiere --native-manifest con URLs y SHA-256 reales')
    build,android_jar,jdk=herramientas(localizar_sdk(sdk))
    source=ROOT/'android/agx_vpn_helper'
    output=Path(output or ROOT/'tools/agx_vpn_helper.apk').resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    suffix='.exe' if os.name=='nt' else ''
    key,environment=clave_local(jdk['keytool'])
    with tempfile.TemporaryDirectory(prefix='agx-helper-build-',dir=output.parent) as folder:
        temporary=Path(folder);classes=temporary/'classes';dex=temporary/'dex'
        natives=preparar_bibliotecas(native_manifest,temporary) if native_manifest else {}
        classes.mkdir();dex.mkdir()
        sources=sorted((source/'src').rglob('*.java'))
        if not sources:
            raise FileNotFoundError('No hay fuentes Java del helper')
        argsfile=temporary/'sources.txt'
        argsfile.write_text('\n'.join('"'+str(path).replace('\\','/')+'"' for path in sources),encoding='utf-8')
        ejecutar([jdk['javac'],'--release','8','-encoding','UTF-8','-classpath',android_jar,
            '-d',classes,'@'+str(argsfile)])
        ejecutar([jdk['java'],'-cp',build/'lib/d8.jar','com.android.tools.r8.D8','--min-api','29',
            '--lib',android_jar,'--output',dex,*sorted(classes.rglob('*.class'))])
        unsigned=temporary/'unsigned.apk';aligned=temporary/'aligned.apk';signed=temporary/'signed.apk'
        ejecutar([build/('aapt'+suffix),'package','-f','-M',source/'AndroidManifest.xml','-I',android_jar,'-F',unsigned])
        with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as package:
            package.write(dex/'classes.dex','classes.dex')
            for abi,entry in natives.items():
                package.write(entry['path'],'lib/'+abi+'/libtun2socks.so')
        # La estructura nativa se comprueba antes de alinear y firmar.
        with zipfile.ZipFile(unsigned) as package:
            embedded=verificar_bibliotecas_apk(package,required=bool(natives) or require_native)
            for abi,entry in natives.items():
                if embedded[abi]['sha256'] != entry['sha256']:
                    raise ValueError('Biblioteca alterada durante el empaquetado: '+abi)
        ejecutar([build/('zipalign'+suffix),'-f','4',unsigned,aligned])
        ejecutar([jdk['java'],'-jar',build/'lib/apksigner.jar','sign','--ks',key,'--ks-key-alias','agx-lab',
            '--ks-pass','env:AGX_KEYSTORE_PASS','--key-pass','env:AGX_KEYSTORE_PASS','--out',signed,aligned],environment=environment)
        # Validar antes de sustituir un artefacto anterior.
        ejecutar([jdk['java'],'-jar',build/'lib/apksigner.jar','verify','--verbose',signed])
        signed.replace(output)
    return verificar_y_registrar_helper(output,report,sdk=sdk)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--native-manifest',type=Path)
    parser.add_argument('--require-native',action='store_true')
    args=parser.parse_args()
    try:
        if args.verify_only:
            if args.require_native:
                with zipfile.ZipFile(args.output or ROOT/'tools/agx_vpn_helper.apk') as package:
                    verificar_bibliotecas_apk(package,required=True)
            verificar_y_registrar_helper(args.output,args.report,sdk=args.sdk)
        else:
            compilar(args.sdk,args.output,args.report,args.native_manifest,args.require_native)
        return 0
    except subprocess.CalledProcessError as exc:
        print('[AGX-BUILD] Falló la herramienta de compilación: '+str(exc.stderr or exc.stdout),file=sys.stderr)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired,zipfile.BadZipFile) as exc:
        print('[AGX-BUILD] '+str(exc),file=sys.stderr)
    return 2


if __name__=='__main__':
    raise SystemExit(main())
