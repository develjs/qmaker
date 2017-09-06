#!/usr/bin/python
# 
# version 1.6.8m
#
# created sdk.json
#	PATHS - for additional paths, 
#	QTKITS - list of founded qt-kits
#	MKSPECS - list of founded mkspecs
#	@todo 
#		clean = false
#		default values for build
#		auto-find using libs
#		message no sdk found
#		require win32-msvc2010,win32-msvc
#		require QT5.4,5,4.8
#		parse pro file for get requires
#		git fail result
#		jso whole folder
#		jso,git,brew,nodejs... move to dependeces

import os,platform,stat
import glob
import re
import urllib
import tarfile
import subprocess
import shutil
import sys
import json,tempfile,distutils
import zipfile

DEBUG = False
LOG = True
DEFAULT_QTKITS = {}
LOG_FILE = os.path.abspath(sys.argv[0]).replace(".py","")+".log"
MIRROR_SERVER = ""

# name of saved file, and using for build
SDK_JSON = os.path.abspath("sdk.json")
#sdk_path = os.path.dirname(os.path.abspath(sys.argv[0])) + '/'+SDK_JSON


# configure dependens
# require qssh
def qssh_static_patch(pkg):
    with open("src/qtcreatorlibrary.pri", "a") as myfile:
        myfile.write("CONFIG-=shared dll\n")
        myfile.write("CONFIG+=staticlib\n")	

def prepare_openssl(pkg):
    cmd = ""
    if os.name=="nt":
        CALL_SDK2("perl Configure VC-WIN32 --prefix="+os.getcwd()+" no-asm" + "\n" + "ms\do_ms")
    else:
        shcall_mac("perl ./Configure darwin64-x86_64-cc")

'''
    "<dep-name>": {
        "name"			: "<dep-name>",
        "url"			: "<URL to arhive>",
        "root"			: "build/root/dir", # root dir for run confgiure,make...
        "result"		: "path/to/result.lib", # if exists then pass download and build steps
        "patch"			: patch_function # patch_function(dep-params) starting from worked dir
    }
'''
DEPS={
    "qtftp"  : {
        "name"			: "qtftp",
        "url"			: "https://github.com/qtproject/qtftp.git",
        "deps"			: ["QT"],
        "make"          : True,
        "result"		: "lib/Qt5Ftp.lib" if os.name=="nt" else "lib/libQt5Ftp.a"
    },
     "openssl": {
        "name"			: "ssleay",
        "url"			: "https://www.openssl.org/source/openssl-1.0.2j.tar.gz",
        "make"          : True,
        "NMAKEFLAGS"	: ' -f ms/nt.mak',
        "result"		: "out32/ssleay32.lib" if os.name=="nt" else "libssl.a",
        "includes"		: "inc32",
        "libs"			: "out32",
        "patch"			: prepare_openssl
    },
    "zlib": {
        "name"			: "zlib",
        "url"			: "http://zlib.net/fossils/zlib-1.2.8.tar.gz",
        "make"          : True,
        "NMAKEFLAGS"	: "-f win32/Makefile.msc" if os.name=="nt" else "",
        "configure"		: "--static",
        "result"		: "zlib.lib" if os.name=="nt" else "libz.a"
    },
    "qthttp": {
        "name"			: "qthttp",
        "url"			: "https://github.com/qtproject/qthttp.git",
        "make"          : True,
        "deps"			: ["QT"],
        "result"		: "lib/Qt5Http.lib" if os.name=="nt" else "lib/libQt5Http.a"
    },
    "QtcSsh": {
        "name"			: "qssh",
        "url"			: "http://master.qt.io/official_releases/qtcreator/3.3/3.3.2/qt-creator-opensource-src-3.3.2.tar.gz",
        "root"			: "src/libs/ssh", # build root dir
        "make"          : True,
        "result"		: "lib/qtcreator/QtcSsh.lib" if os.name=="nt" else "src/libs/ssh/libQtcSsh.a", 
        "MAKEFLAGS"		: 'CXXFLAGS="-std=c++11 -stdlib=libc++"',
        "deps"			: ["QT"],
        "patch"			: qssh_static_patch # starting from worked dir
    },
    "cryptopp": {
        "name"			: "cryptopp",
        "url"			: "http://www.cryptopp.com/cryptopp562.zip",
        "make"          : True,
        "MAKEFLAGS"		: 'CXXFLAGS="-std=c++11 -stdlib=libstdc++ -DCRYPTOPP_DISABLE_ASM -Wno-c++11-narrowing" static',
        "result"		: "cryptopp.lib" if os.name=="nt" else "libcryptopp.a"
    }
}


# libssh2
def libssh2_patch_mac(pkg):
    check_brew()
    os.system("brew install libssh2")
    return
    
if os.name=="nt":
    DEPS["libssh2"] = {
        "name"			:"libssh2",
        "url"			:"https://www.libssh2.org/download/libssh2-1.7.0.tar.gz",
        "deps"			: ["openssl"],
        "make"          : True,
        "configure"		: "--with-libssl-prefix=../openssl",
        "msvc_proj"		: "../libssh2_vs2010/libssh2.vcxproj",
        "result" 		:"Release_lib/libssh2.lib",
    }
else:
    DEPS["libssh2"] = {
        "name"			: "libssh2",
        "make"          : True,
        "result" 		: "/usr/local/lib/libssh2.a",
        "patch"			: libssh2_patch_mac
    }
    
    
# libcurl
# based on  https://github.com/biasedbit/curl-ios-build-scripts
# with some improvements
def libcurl_set_path(pkg):
    if os.name=="nt":
        os.environ["OPENSSL_PATH"]=os.getcwd()+'/../openssl'
        os.environ["LIBSSH2_PATH"]=os.getcwd()+'/../libssh2'
        os.environ["ZLIB_PATH"] = os.getcwd() + '/../zlib'
    else:
        os.chdir("../..")
        sdk_json = get_sdk()
        os.chdir("tools/libcurl")
        # calc sdk
        sdk = "10.9" #default
        if ("QMAKE_MAC_SDK" in sdk_json):
            print "QMAKE_MAC_SDK"
            sdk = sdk_json["QMAKE_MAC_SDK"].replace("macosx","")
        
        os.system(
              "./build_curl --archs x86_64 --enable-protocols ftp --disable-protocols rtsp, ldap, ldaps, dict, telnet, tftp, pop3, imap, smtp, gopher "
            + "--enable-flags ssl,libssh2=/usr/local,zlib=" + os.getcwd() + "../tools/zlib "
            + "--sdk-version " + sdk + " --osx-sdk-version " + sdk + " --no-cleanup"
        )
    

if os.name=="nt":
    DEPS["libcurl"] = {# ./configure --disable-shared --with-libssh2=../libssh2/ --with-ssl=../openssl/ --with-zlib=../zlib/
        "name"			:"libcurl",
        "url"			:"https://curl.haxx.se/download/curl-7.50.3.tar.gz",
        "root"			:"lib",
        "deps"			: ["openssl"],
        "NMAKEFLAGS"	: '/f makefile.vc10 CFG="release-ssl-ssh2-zlib"',
        "result"		: "lib/libcurl.lib",
        "patch"			: libcurl_set_path
    }
else:
    DEPS["libcurl"] = {# git clone -b master --single-branch --depth 1 https://github.com/biasedbit/curl-ios-build-scripts ./build_curl
        "url"			: "https://github.com/develjs/curl-ios-build-scripts.git",
        "name"			:"libcurl",
        "root"			:"../libcurl",
        "result"		: "../libcurl/curl/osx/lib/libcurl.a",
        "patch"			: libcurl_set_path
    }	



def main():
    if sys.platform == 'darwin':
        if not os.path.exists(SDK_JSON):
            init_mac_sdk()
            
    if sys.platform == 'win32': # todo: move to mac too
        check_sdk(False) # once
        sdk = get_sdk()
        if not "QMAKESPEC" in sdk or not "QTDIR" in sdk:
            find_sdk_win()


# --------------------------------------------------

def check_sdk(recheck = True):
    sdk = get_sdk()
    
    if recheck or not "MKSPECS" in sdk:
        print("search for MKSPECS...")
        set_sdk_param("MKSPECS", find_mkspecs_win())
        sdk = get_sdk()
    
    
    if recheck or not "QTKITS" in sdk:
        print("search for QTKITS...")
        all_qtkits = findQt()
        qtkits={}
        for mkspec in sdk["MKSPECS"]:
            if mkspec in all_qtkits:
                qtkits[mkspec] = all_qtkits[mkspec]
        set_sdk_param("QTKITS", qtkits)
        
    if not "PATHS" in sdk:
        set_sdk_param("PATHS", [])
        
    
    
def init_mac_sdk():
    MKSPECS=["macx-g++","macx-xcode"]
    #export QMAKESPEC="macx-xcode"
    QMAKESPEC=MKSPECS[0]
    
    QTDIR=""
    if "QTDIR" in os.environ:
        QTDIR=os.environ["QTDIR"]

    if QTDIR=="":
        QTDIR=findQTbyMKSPECS(MKSPECS)
    

    
    # ---- save SDK bat ----			
    # output variables and comment
    #f_out=open(SDK_FILE, "w")

    # QMAKESPEC
    #f_out.write("export QMAKESPEC="+QMAKESPEC+"\n")
    #for spec in MKSPECS:
    #	f_out.write("#export QMAKESPEC="+spec+"\n")
    #f_out.write("\n")
    
    #QTDIR
    #f_out.write("export QTDIR="+QTDIR+"\n")
    #for spec in MKSPECS:
    #	for path in DEFAULT_QTKITS[spec]:
    #		if os.path.exists(path):
    #			f_out.write("#export QTDIR="+path+"\n")
    #f_out.write("\n")
    
    
    # run sdk
    #f_out.write("export PATH=$PATH:$QTDIR/bin\n")
    #f_out.write("\n")
    #f_out.close()
    
    sdk = {
        "QMAKESPEC": QMAKESPEC,
        "QTDIR":QTDIR
    }
    
    # fix for QT 5.3 that default compiling for macosx10.8
    ver=platform.mac_ver()[0].split(".")
    if ver[0]>=10 and ver[1]>=8:
        sdk["QMAKE_MAC_SDK"] = "macosx10.9"
    write_json(sdk)
    
    return
    
def findQTbyMKSPECS(MKSPECS):
    for spec in MKSPECS:
        if not spec in DEFAULT_QTKITS:
            continue
        for path in DEFAULT_QTKITS[spec]:
            if os.path.exists(path):
                return path
    return ""

    
# vs sdk enviroment
VSCOMNTOOLS = {
    "win32-msvc2015":"VS140COMNTOOLS",
    "win32-msvc2013":"VS120COMNTOOLS",
    "win32-msvc2012":"VS110COMNTOOLS",
    "win32-msvc2010":"VS100COMNTOOLS",
    "win32-msvc2008":"VS90COMNTOOLS"
}

WIN_MKSPECS = [
    "win32-msvc2015",
    "win32-msvc2013",
    "win32-msvc2012",
    "win32-msvc2010",
    "win32-msvc2008"
]

# find existing win mkspecs
def find_mkspecs_win():
    mkspecs = []
    for spec in WIN_MKSPECS:
        if VSCOMNTOOLS[spec] in os.environ:
            mkspecs.append(spec)
    
    return mkspecs


# empyric function for detect SDK and QT
def find_sdk_win():

    sdk = get_sdk()
    MKSPECS = sdk["MKSPECS"] # get existing 
    QTKITS = sdk["QTKITS"]

    # --------- check preseted ---------
    QTDIR = ""
    #if "QTDIR" in os.environ:
    #	QTDIR = os.environ["QTDIR"]

    QMAKESPEC=""
    #if "QMAKESPEC" in os.environ:
    #	QMAKESPEC = os.environ["QMAKESPEC"]
    
    
    # ---- search in DEFAULT_QTKITS ----
    for spec in MKSPECS:
        if spec in QTKITS and spec in DEFAULT_QTKITS: # existing
            for path in DEFAULT_QTKITS[spec]:
                if os.path.exists(path):
                    QTDIR = path
                    QMAKESPEC = spec
                    break
    
    # select optinal kit if not select in default
    if QTDIR=="" or QMAKESPEC=="":
        for spec in QTKITS:
            for qt in QTKITS[spec]:
                if QTDIR=="" or len(QTDIR)>len(qt["QTDIR"]): # minimum customisation
                    QTDIR = qt["QTDIR"]
                    QMAKESPEC = spec
    
    if "QTDIR" != "":
        set_sdk_param("QTDIR", QTDIR)
        
    if "QMAKESPEC" != "":
        set_sdk_param("QMAKESPEC", QMAKESPEC)
    
    return
    

def write_json(params):
    f_out=open(SDK_JSON, "w")
    f_out.write(
        json.dumps(params, indent=4, separators=(',', ': '))
    )
    f_out.close()
    return
    
def write_sdk_json(QMAKESPEC,QTDIR):
    write_json({
        "QMAKESPEC": QMAKESPEC,
        "QTDIR":QTDIR
    })
    return

def set_sdk_param(name,value):
    params = get_sdk()
    params[name] = value
    write_json(params)
    return
    
def getFile(path):
    with open(path, 'r') as file:
        data = file.read()
        file.close()
    return data

def writeFile(path, data):
    with open(path, "w") as f_out:
        f_out.write(data)
        f_out.close()
    return


def get_sdk():
    sdk_path = SDK_JSON
    params = {}
    if os.path.exists(sdk_path):
        with open(sdk_path, 'r') as f:
            try:
                params = json.load(f)
            except:
                pass
                
    return params
    
# get sdk variable and check in eviroment
def get_sdk_var(name):
    sdk = get_sdk()
    if name in sdk:
        return sdk[name]
    if name in os.environ:
        return os.environ[name]
    return ""

    
# ----------------------- BUILDING --------------------------
'''
pkg = {
    "name"			: "<Name>",
    "url"			: "<URL to arhive>",
    "root"			: "build/root/dir", 
    "result"		: "path/to/result.lib", 
    "patch"			: path_function # starting from worked dir
}
'''

def prepare_pkg(pkg, workdir):
    workdir = os.path.abspath(workdir).replace("\\","/")
    
    # check dependence exists
    if "check" in pkg:
        if pkg["check"](workdir):
            return True
    
    # if result is exists then stop
    if "result" in pkg:
        if os.path.exists(workdir + "/" + pkg["result"]):
            return True
    else: # or package directory is not empty
        if os.path.isdir(workdir) and os.listdir(workdir):
            return True
    
    if not os.path.exists(workdir):
        os.makedirs(workdir)
        
    if "svn" in pkg:
        if not svn(pkg["svn"], workdir):
            return False
            
    if "url" in pkg:
        fname = download(pkg["url"], workdir, mirror=True)
        if fname=="-":
            return True
        
    if not "root" in pkg: 
        pkg["root"] = ""
        

    if not "configure" in pkg: 
        pkg["configure"]=""	
    if not "deps" in pkg:
        pkg["deps"]=[]
    
    
    # patch if need
    if "patch" in pkg:
        cdir = os.getcwd()
        os.chdir(workdir)
        pkg["patch"](pkg)
        os.chdir(cdir) # revert current dir
    
    
    if "make" in pkg:
        # build if has lib name
        if not "name" in pkg:
            return True
            
        if not "MAKEFLAGS" in pkg: 
            pkg["MAKEFLAGS"]=""
        if not "QMAKEFLAGS" in pkg: 
            pkg["QMAKEFLAGS"]=""
        if pkg["result"][0] != "/":
            pkg["result"] = workdir + "/" + pkg["result"]

        sdk_json = get_sdk()
        QMAKEFLAGS=pkg["QMAKEFLAGS"]
        if ("QMAKE_MAC_SDK" in sdk_json):
            QMAKEFLAGS = QMAKEFLAGS + " QMAKE_MAC_SDK=\"" + sdk_json["QMAKE_MAC_SDK"] + "\""
        
        if "QT" in pkg["deps"]:
            buildQmakeMake2(pkg["name"], workdir + "/" + pkg["root"], pkg["result"], sdk_json["QTDIR"], sdk_json["QMAKESPEC"], MAKEFLAGS=pkg["MAKEFLAGS"], QMAKEFLAGS=QMAKEFLAGS)
        else:
            prepareMake2(pkg["name"], workdir + "/" + pkg["root"], pkg["result"], sdk_json["QMAKESPEC"], params=pkg)
    

        
    # check result is exists
    if "result" in pkg:
        if not os.path.exists(pkg["result"]):
            return False
        # copy result to workdir
        # ?? copy to root dir
        copy_to = workdir + "/" + pkg["root"] + "/" + os.path.basename(pkg["result"])
        if not os.path.exists(copy_to):
            shutil.copyfile(pkg["result"], copy_to)
    
    else: # or package directory is not empty
        if not os.listdir(workdir):
            return False


    return True


# downloading file 
# http: or git: or svn: (svn+file: || svn+http:)
# @param url - download from
# @param to - folder to
# @return String
def download(url, to, mirror = False):

    # get with git
    if (url.startswith("git:") or url.endswith(".git")):
        os.system("git clone -b master " + url + " " + to)
        return to
        
    if url.startswith("svn"):
        url = url.replace("svn+http:", "http:")
        url = url.replace("svn+file:", "file:")
        if not os.path.exists(to):
            os.system("svn checkout " + url + " " + to)
        else: 
            os.system("svn update -q " + to)
        return to

    fname = to + "/" + url[ url.rindex('/')+1: ]
    print mirror 
    print  MIRROR_SERVER
    if mirror and MIRROR_SERVER:
        mirror_path = smb_mount(MIRROR_SERVER)
        try:
            mir_url = make_mirror(url, mirror_path)
            shutil.copy(mir_url, fname)
        finally:
            smb_umount(mirror_path)
    else:
        fname = download_file(url, fname)

    if os.path.exists(fname):
        extract(fname)
        print("ok")
        return fname
    else:
        print("fail")
        return "-"


# url - url download from 
# fname - file download to (as "file.zip") or folder (as "folder/")
def download_file(url, fname):
    if fname.endswith("/"):
        fname += url[ url.rindex('/')+1: ]

    # download if need
    if not os.path.exists(fname):
        if not os.path.exists(fname[0: fname.rindex('/')]):
            os.makedirs(fname[0: fname.rindex('/')])
            
        print ("downloading to " + fname + "...")
        try:
            # For Python 3.0 and later
            from urllib.request import urlretrieve
            urllib.request.urlretrieve(url, fname)
        except ImportError:
            # Fall back to Python 2's urllib2
            urllib.urlretrieve(url, fname)

    return fname


# make url mirror
# @todo define default repo_path   
def make_mirror(url, repo_path):
    path = re.sub("^http[s]?\:\/\/","",url)
    path = repo_path + "/" + path
    
    # download if need 
    if not os.path.exists(path):
        path = download_file(url, path)

    return path


# extracting archive to dir of archive-file
def extract(fname, fdir=""):
    fname = os.path.abspath(fname)
    if fdir=="":
        fdir = os.path.dirname(fname)
    if not os.path.exists(fdir):
        os.makedirs(fdir)

    # clean previous extracted files
    for f in os.listdir(fdir):
        if os.path.basename(fname) != f:
            if os.path.isdir(fdir+"/"+f):
                shutil.rmtree(fdir+"/"+f, ignore_errors=True)
            else:
                os.remove(fdir+"/"+f)
    
    
    # calc tmp dir
    tmpdir = fdir.replace("\\","/") + "/tmp"
    
    # extracting to tmp
    print ("extracting " + fname + " ...")
    
    if (fname.endswith(".tar.gz") or fname.endswith(".tar")):
        ar = tarfile.open(fname)
        ar.extractall(tmpdir)
        ar.close()
    elif(fname.endswith(".zip")):
        os_unzip(fname, tmpdir)
        #ar = zipfile.ZipFile(fname)
        #ar.extractall(tmpdir)
        #ar.close()
    else:
        print("Error: archive has unrecognesed format " + fname)
        return "-"
    rootdir = tmpdir
    # if archive has one dir then use its content
    if len(os.listdir(rootdir))==1:
        rootdir = rootdir + "/" + os.listdir(rootdir)[0];
    
        
    # move extracted files to root
    for f in os.listdir(rootdir):
        shutil.move(rootdir+"/"+f, fdir)
    
    # delete tmp dir
    shutil.rmtree(tmpdir, ignore_errors=True)
        
    return ""


# addEnv - additional enviroment
# todo: join with buildQmakeMake2
def prepareMake2(libname, buildRootDir, buildResult, QMAKESPEC, params=[]):

    _params = {
        "MAKEFLAGS" : "",
        "configure": "", # configure addition params
        "NMAKEFLAGS": "",
        "msvc_proj": "",
        "msvc_conf": "Release"
    }
    _params.update(params)
    
    # pass build if result exists
    if os.path.exists(buildResult):
        print(buildResult + " is exist")
        return ""
    
    print("")
    print("starting build " + libname + "...")
    
    cmd = []
    cmd.append("cd " + buildRootDir)
    
    # do configure
    configure = "configure" + (".exe" if os.name=="nt" else "")
    if os.path.isfile(buildRootDir + "/" + configure):
        cmd.append((".\\" if os.name=="nt" else "./") +	configure + " " + _params["configure"])
    
    if QMAKESPEC.startswith("win32-msvc") and len(_params["msvc_proj"])>0 and os.path.isfile(buildRootDir + "/" + _params["msvc_proj"]):
        cmd.append("msbuild /clp:ErrorsOnly " + buildRootDir + "/" + _params["msvc_proj"] + " /t:Rebuild /property:Configuration=" + _params["msvc_conf"] + " /verbosity:quiet")
    else:
        if QMAKESPEC.startswith("win32-msvc"):
            cmd.append("nmake "+ _params["NMAKEFLAGS"])
        else:
            cmd.append('make ' + _params["MAKEFLAGS"])
    
    cmds = "\n".join(cmd)
    
    if os.name=="nt":
        CALL_SDK2(cmds, {})
    else:
        CALL_WRAP(cmds, {}) # todo: change to CALL_SDK2
    
    # check result
    if os.path.exists(buildResult):
        print("build Ok!")
        return buildResult
    else:
        print("build Fail!")
        return "-"	


def buildQmakeMake2(libname, buildRootDir, buildResult, QTDIR, QMAKESPEC, MAKEFLAGS="", QMAKEFLAGS=""):
    
    if os.path.exists(buildResult):
        print(buildResult + " is exist")
        return ""
        
    print("")
    print("starting build " + libname + "...")
    
    cmd = []
    cmd.append("cd " + buildRootDir)
    if os.name=="nt":
        cmd.append("nmake clean")
    else:
        cmd.append('make clean')
        
    cmd.append('qmake' + " " + QMAKEFLAGS)
    
    if os.name=="nt":
        cmd.append("nmake")
    else:
        cmd.append('make '+MAKEFLAGS)
        #cmd.append("make install")


    new_sdk = {}
    if QTDIR != "":
        new_sdk["QTDIR"] = QTDIR
    if QMAKESPEC=="":
        new_sdk["QMAKESPEC"] = QMAKESPEC
    
    CALL_SDK2("\n".join(cmd), new_sdk)

    
    # check result
    if os.path.exists(buildResult):
        print("build Ok!")
        return buildResult
    else:
        print("build Fail!")
        return "-"	


# microsoft sign tool 
# params name, key, password, timestamp, desc, url
def sign2(exe, name="", key="", password="",  QMAKESPEC = "", timestamp="", desc="", url=""):
    if len(QMAKESPEC)==0:
        QMAKESPEC = get_sdk()["QMAKESPEC"]
    shcall(
        '@call "%'+VSCOMNTOOLS[QMAKESPEC]+'%vsvars32.bat" > nul \n'
        + "signtool.exe sign /a"
        + (" /f \"" + key.replace("/","\\") + "\"" if len(key) else "")
        + (" /p \"" + password + "\"" if len(password) else "")
        + (" /n \"" + name + "\"" if len(name) else "")
        + (" /t \"" + timestamp + "\"" if len(timestamp) else "")
        + (" /d \"" + desc + "\"" if len(desc) else "")
        + (" /du \"" + url + "\"" if len(url) else "")
        + " " + exe.replace("/","\\"),
        log = LOG
    )
    if len(key):
        print ("Warning: avoid to use local key for signing")
    
    
    
    
# create qrc with dirs files list
def dir2qrc(dirPath, outFile, prefix="", alias_prefix=""):
    outFile = os.path.abspath(outFile)

    filelist=[];
    
    
    cdir = os.getcwd()
    os.chdir(dirPath)
    for root,dirs,files in os.walk("./"):
        for name in files:
            filelist.append(os.path.join(root, name).replace("\\","/"))
    os.chdir(cdir) # revert current dir
    
    filelist = sorted(filelist)
    
    f_out=open(outFile, "w")
    f_out.write("<RCC>\n" 
        + '\t<qresource prefix="/">\n')
                    
    for file in filelist:
        if len(alias_prefix):
            f_out.write('\t\t<file alias="'+file.replace("./", alias_prefix)+'">'); # alias="'+file+'"
        else:
            f_out.write('\t\t<file>');
        f_out.write(file.replace("./",prefix) + "</file>\n"); 
    
    f_out.write("\t</qresource>\n" 
            + "</RCC>")
    f_out.close()

    return	
    
'''
def file_replace(filename, old_string, new_string):
    content = open(filename).read()
    content = content.replace(old_string, new_string)
    f = open(filename, 'w')
    f.write(content)
    f.close()
    return
'''
    

# path using with /
# PATH enviroment use ; as separator
# and replace %PATH% -> $PATH
def CALL_SDK2(cmds, new_sdk = {}, addEnv={}, sys_adopt=True, runpath=""):
    sdk = get_sdk()
    sdk.update(new_sdk) # todo: check empty values
    
    addEnv["PATH"] = ""
    if "PATHS" in sdk:
        addEnv["PATH"] = ';'.join(sdk["PATHS"])
    
    if "QTDIR" in sdk:
        addEnv["QTDIR"] = sdk["QTDIR"]
        
        if addEnv["PATH"] != "":
            addEnv["PATH"] = addEnv["PATH"] + ";"
        addEnv["PATH"] = addEnv["PATH"] + addEnv["QTDIR"] + "/bin"
    
    if "QMAKESPEC" in sdk:
        addEnv["QMAKESPEC"] = sdk["QMAKESPEC"]
        
        if addEnv["QMAKESPEC"] in VSCOMNTOOLS:
            cmds = '@call "%' + VSCOMNTOOLS[addEnv["QMAKESPEC"]] + '%vsvars32.bat" > nul\n' + cmds
    
    if addEnv["PATH"] == "":
        addEnv.pop("PATH", None)
    else:
        addEnv["PATH"] = "%PATH%;" + addEnv["PATH"]

    res = CALL_WRAP(cmds, addEnv=addEnv, sys_adopt=sys_adopt, runpath=runpath)

    return res["status"]
        
def CALL_SDK3(cmds, new_sdk = {}, addEnv={}, sys_adopt=True, runpath=""):
    sdk = get_sdk()
    sdk.update(new_sdk) # todo: check empty values
    
    addEnv["PATH"] = ""
    if "PATHS" in sdk:
        addEnv["PATH"] = ';'.join(sdk["PATHS"])
    
    if "QTDIR" in sdk:
        addEnv["QTDIR"] = sdk["QTDIR"]
        
        if addEnv["PATH"] != "":
            addEnv["PATH"] = addEnv["PATH"] + ";"
        addEnv["PATH"] = addEnv["PATH"] + addEnv["QTDIR"] + "/bin"
    
    if "QMAKESPEC" in sdk:
        addEnv["QMAKESPEC"] = sdk["QMAKESPEC"]
        
        if addEnv["QMAKESPEC"] in VSCOMNTOOLS:
            cmds = '@call "%' + VSCOMNTOOLS[addEnv["QMAKESPEC"]] + '%vsvars32.bat" > nul\n' + cmds
    
    if addEnv["PATH"] == "":
        addEnv.pop("PATH", None)
    else:
        addEnv["PATH"] = addEnv["PATH"]+";%PATH%"

    res = CALL_WRAP(cmds, addEnv=addEnv, sys_adopt=sys_adopt, runpath=runpath)

    return res
    
def rcc(in_qrc, out_rcc):
    CALL_SDK2('rcc -binary "'+in_qrc+'"  -o "'+out_rcc+'" ')


# copy_files([srcBundle], MAKE_PATH)
def copy_files(files, dest, text=""):
    if len(text):
        print("Copy " + text + "..."),
    
    if not os.path.exists(dest):
        os.makedirs(dest)
        
    for mask in files:
        file_list = glob.glob(mask)
        if len(file_list) > 0:
            for file in file_list:
                if os.path.isdir(file):
                    if os.path.exists(dest+"/"+os.path.basename(file)):
                        shutil.rmtree(dest+"/"+os.path.basename(file))
                    shutil.copytree(file, dest+"/"+os.path.basename(file))
                else:
                    shutil.copy(file, dest)
                    
        else:
            print('\nWarning: file not found - '+mask)
    
    if len(text):
        print ("done")
    return



    
# ---- DEPLOY
def deploy_vs(QMAKESPEC, MAKE_PATH):
    if QMAKESPEC=="win32-msvc2012":
        vs2012(MAKE_PATH)
    elif QMAKESPEC=="win32-msvc2010":
        vs2010(MAKE_PATH)
    elif QMAKESPEC=="win32-msvc2008":
        vs2008(MAKE_PATH)
    else:
        return False
    return True
    
# copy OpenSSL dlls 
def deploy_sll(MAKE_PATH):
    copy_files([
            os.environ["SystemRoot"]+"\\SysWOW64\\libeay32.dll",
            os.environ["SystemRoot"]+"\\SysWOW64\\libssl32.dll",
            os.environ["SystemRoot"]+"\\SysWOW64\\ssleay32.dll"
        ],
        MAKE_PATH
    )
    return


# for deploy vs redist package and qt
WINDEPLOY_DEF_REMOVE = [ "accessible","audio","bearer","iconengines","printsupport","sensor*","position","playlistformats","mediaservice","*/qdds.dll", "*/qwbmp.dll","*/qtga.dll","*/qtiff.dll","*/qsvg.dll","sqldrivers" ]
def deploy_qt2(app_path, QTDIR="", QMAKESPEC="", mod={}, remove=WINDEPLOY_DEF_REMOVE):
    sdk_json = get_sdk()
    if QTDIR=="":
        QTDIR=sdk_json["QTDIR"]
    if QMAKESPEC=="":
        QMAKESPEC=sdk_json["QMAKESPEC"]
    
    if os.name=="nt":
        if os.path.exists(QTDIR+"\\bin\\QtCore4.dll"):
            qt4(QTDIR,  os.path.dirname(os.path.abspath(app_path)))
        else:
            windeployqt(app_path, QTDIR, QMAKESPEC, mod)
        
        deploy_vs(QMAKESPEC, os.path.dirname(os.path.abspath(app_path)))
        
    # remove some
    cdir = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(app_path)))
    try:
        for mask in remove:
            file_list = glob.glob(mask)
            for file in file_list:
                if os.path.isdir(file):
                    shutil.rmtree(file)
                else:
                    os.remove(file)
    finally:
        os.chdir(cdir) # revert current dir
        

def deploy_qt(QTDIR, MAKE_PATH):
    if os.path.exists(QTDIR+"\\bin\\Qt5Core.dll"):
        qt5(QTDIR, MAKE_PATH)
    elif os.path.exists(QTDIR+"\\bin\\QtCore4.dll"):
        qt4(QTDIR, MAKE_PATH)
    else:
        return False
    return True
    
def qt5(QTDIR,MAKE_PATH):
    
    copy_files([
        QTDIR+"\\bin\\Qt5Core.dll",
        QTDIR+"\\bin\\Qt5Gui.dll",
        QTDIR+"\\bin\\Qt5WebKit.dll",
        QTDIR+"\\bin\\Qt5WebKitWidgets.dll",
        QTDIR+"\\bin\\Qt5Widgets.dll",
        QTDIR+"\\bin\\Qt5Script.dll"
        ], 
        MAKE_PATH)
        
    copy_files([
        QTDIR+"\\plugins\\imageformats\\qjpeg.dll",
        QTDIR+"\\plugins\\imageformats\\qgif.dll",
        QTDIR+"\\plugins\\imageformats\\qico.dll",
        QTDIR+"\\plugins\\imageformats\\qmng.dll"
        ],
        MAKE_PATH+"\\plugins\\imageformats\\")
        
    copy_files([
        QTDIR+"\\plugins\\platforms\\qwindows.dll"
        ], 
        MAKE_PATH+"\\platforms")
    
    # other unnecessary
    copy_files([
        QTDIR+"\\bin\\icudt5*.dll",
        QTDIR+"\\bin\\icuin5*.dll",
        QTDIR+"\\bin\\icuuc5*.dll",
        QTDIR+"\\bin\\libEGL.dll",
        QTDIR+"\\bin\\libGLESv2.dll",
        QTDIR+"\\bin\\Qt5Network.dll",
        QTDIR+"\\bin\\Qt5OpenGL.dll",
        QTDIR+"\\bin\\Qt5PrintSupport.dll",
        QTDIR+"\\bin\\Qt5Qml.dll",
        QTDIR+"\\bin\\Qt5Quick.dll",
        QTDIR+"\\bin\\Qt5Sensors.dll",
        QTDIR+"\\bin\\Qt5Sql.dll",
        QTDIR+"\\bin\\Qt5V8.dll",
        QTDIR+"\\bin\\Qt5Multimedia.dll",
        QTDIR+"\\bin\\Qt5Positioning.dll",
        QTDIR+"\\bin\\Qt5MultimediaWidgets.dll"
        ], 
        MAKE_PATH)
    return True


def qt4(QTDIR,MAKE_PATH):
    copy_files([
        QTDIR+"\\bin\\QtCore4.dll",
        QTDIR+"\\bin\\QtGui4.dll",
        QTDIR+"\\bin\\QtNetwork4.dll",
        QTDIR+"\\bin\\QtXml4.dll",
        QTDIR+"\\bin\\QtScript4.dll",
        QTDIR+"\\bin\\QtWebKit4.dll",
        QTDIR+"\\bin\\phonon4.dll",
        QTDIR+"\\bin\\QtXmlPatterns4.dll"
        ],
        MAKE_PATH)
    
    copy_files([
        QTDIR+"\\plugins\\imageformats\\qjpeg4.dll",
        QTDIR+"\\plugins\\imageformats\\qgif4.dll"
        ],
        MAKE_PATH+"\\plugins\\imageformats")

    return True


    
def vs2012(MAKE_PATH):
    # xcopy "%windir%\System32\msvcr110.dll" "%MAKE_PATH%\" /Y /R /D
    # xcopy "%windir%\System32\msvcp110.dll" "%MAKE_PATH%\" /Y /R /D
    copy_files([
        os.environ["SystemRoot"]+"\\SysWOW64\\msvcr110.dll",
        os.environ["SystemRoot"]+"\\SysWOW64\\msvcp110.dll"
        ],
        MAKE_PATH)

    return True

def vs2010(MAKE_PATH):
    # xcopy "%windir%\System32\msvcr100.dll" "%MAKE_PATH%\" /Y /R /D
    # xcopy "%windir%\System32\msvcp100.dll" "%MAKE_PATH%\" /Y /R /D
    copy_files([
        os.environ["SystemRoot"]+"\\SysWOW64\\msvcr100.dll",
        os.environ["SystemRoot"]+"\\SysWOW64\\msvcp100.dll"
        ],
        MAKE_PATH)
    
    return True

def vs2008(MAKE_PATH):
    # check VCINSTALLDIR
    if "VCINSTALLDIR" in os.environ:
        VCINSTALLDIR=os.environ["VCINSTALLDIR"]
    else:
        VCINSTALLDIR=os.environ["ProgramFiles"]+"\Microsoft Visual Studio 9.0\VC"
    if not os.path.exists(dest):
        print ("Warning: can't resolve MSVC installation directory (VCINSTALLDIR not defined)")
        return False
    
    
    copy_files([
        VCINSTALLDIR+"\\redist\\x86\\Microsoft.VC90.CRT\\Microsoft.VC90.CRT.manifest",
        VCINSTALLDIR+"\\redist\\x86\\Microsoft.VC90.CRT\\msvcp90.dll",
        VCINSTALLDIR+"\\redist\\x86\\Microsoft.VC90.CRT\\msvcr90.dll"
        ], 
        MAKE_PATH)
    
    return True

def windeployqt(app_path, QTDIR, QMAKESPEC, mod={}):
    DEF_MODULES = {
        "bluetooth"	: False,
        "system-d3d-compiler"	: False,
    #	"plugins": False,
        "translations"	: False
    }
    
    need_mod = ""
    for m in DEF_MODULES:
        need = mod[m] if m in mod else DEF_MODULES[m]
        need_mod = need_mod + (" -" if need else " --no-") + m

        
    new_sdk = {}
    if QTDIR != "":
        new_sdk["QTDIR"] = QTDIR
    if QMAKESPEC=="":
        new_sdk["QMAKESPEC"] = QMAKESPEC
    
    CALL_SDK2("windeployqt.exe --verbose 0" + need_mod + " " + app_path, new_sdk)
    
    
    return	
'''
> windeployqt.exe
 -?, -h, --help             Displays this help.
 -v, --version              Displays version information.
 --dir <directory>          Use directory instead of binary directory.
 --libdir <path>            Copy libraries to path.
 --debug                    Assume debug binaries.
 --release                  Assume release binaries.
 --force                    Force updating files.
 --dry-run                  Simulation mode. Behave normally, but do not
                            copy/update any files.
 --no-plugins               Skip plugin deployment.
 --no-libraries             Skip library deployment.
 --qmldir <directory>       Scan for QML-imports starting from directory.
 --no-quick-import          Skip deployment of Qt Quick imports.
 --no-translations          Skip deployment of translations.
 --no-system-d3d-compiler   Skip deployment of the system D3D compiler.
 --compiler-runtime         Deploy compiler runtime (Desktop only).
 --no-compiler-runtime      Do not deploy compiler runtime (Desktop only).
 --webkit2                  Deployment of WebKit2 (web process).
 --no-webkit2               Skip deployment of WebKit2.
 --json                     Print to stdout in JSON format.
 --list <option>            Print only the names of the files copied.
                            Available options:
                             source:   absolute path of the source files
                             target:   absolute path of the target files
                             relative: paths of the target files, relative
                                       to the target directory
                             mapping:  outputs the source and the relative
                                       target, suitable for use within an
                                       Appx mapping file
 --verbose <level>          Verbose level.


Qt libraries can be added by passing their name (-xml) or removed by passing
the name prepended by --no- (--no-xml). Available libraries:
 
 bluetooth clucene concurrent core declarative designer designercomponents
enginio gui qthelp multimedia multimediawidgets multimediaquick network nfc
opengl positioning printsupport qml quick quickcompilerruntime quickparticles
quickwidgets script scripttools sensors serialport sql svg test webkit
webkitwidgets websockets widgets winextras xml xmlpatterns
'''	
    
# -------
# @params - additional params
def QMAKE2(pro_file, QMAKE_CONFIG="", RELEASE_SUFFIX="", params={}, APP_NAME="", CLEAN=True, CLEAN_ONLY=False):
    if len(APP_NAME)==0:
        proname = os.path.basename(pro_file)
        APP_NAME = proname.replace(".pro","")

    sdk_json = get_sdk()
    for p in params:
        sdk_json[p] = params[p]
    
    QMAKEFLAGS = ""
    if ("QMAKE_MAC_SDK" in sdk_json):
        QMAKEFLAGS = QMAKEFLAGS + " QMAKE_MAC_SDK=\"" + sdk_json["QMAKE_MAC_SDK"] + "\""
    
    if os.name=="nt":
        return qmake_vs(pro_file, QMAKE_CONFIG, sdk_json["QMAKESPEC"], sdk_json["QTDIR"], QMAKEFLAGS)
    else:
        return qmake_mac(pro_file, QMAKE_CONFIG, sdk_json["QMAKESPEC"], sdk_json["QTDIR"], RELEASE_SUFFIX, QMAKEFLAGS, APP_NAME, CLEAN, CLEAN_ONLY)
    
    
def QMAKE(pro_file, QMAKE_CONFIG, QMAKESPEC, QTDIR, RELEASE_SUFFIX="", QMAKEFLAGS="", APP_NAME=""):
    if os.name=="nt":
        return qmake_vs(pro_file, QMAKE_CONFIG, QMAKESPEC, QTDIR, QMAKEFLAGS)
    else:
        return qmake_mac(pro_file, QMAKE_CONFIG, QMAKESPEC, QTDIR, RELEASE_SUFFIX, QMAKEFLAGS, APP_NAME)
    
    
def qmake_vs(pro_file, QMAKE_CONFIG, QMAKESPEC, QTDIR, QMAKEFLAGS=""):
    # you can non-define
    # call sdk.cmd
    # ----------------------------------------------------------------------------
    QTDIR=QTDIR.replace("/","\\")
    sdk = {
        "QTDIR":QTDIR,
        "QMAKESPEC":QMAKESPEC,
        "PATH":"%PATH%;" + QTDIR + "\\bin"
    }
    
    # common update
    # clean all
    for fd in "*.ncb;*.sln;*.suo;*.vcproj;*.idb;*.pdb;*.filters;*.vcxproj;*.vcproj".split(";"):
        for fl in glob.glob(fd):
            os.remove(fl)
    shutil.rmtree("tmp\full", ignore_errors=True)
    

    # qmake	
    print ("qmaking...")
    VSCOMNTOOL = 'call "%'+VSCOMNTOOLS[QMAKESPEC]+'%vsvars32.bat"\n'
    PROJ_EXT = "vcproj" if QMAKESPEC=="win32-msvc2008" else "vcxproj"
    shcall(
        VSCOMNTOOL
        + "qmake "+QMAKEFLAGS+" "+pro_file+" -t vcapp -r -spec "+QMAKESPEC+' "CONFIG+='+QMAKE_CONFIG+'"'+" -o "+pro_file+"."+PROJ_EXT
        , sdk,
        log = LOG
    )

    # patch project file
    if QMAKESPEC=="win32-msvc2008":
        print ("patch project file")
        file_replace(pro_file+"."+PROJ_EXT, "ProgramDatabaseFile", "RandomizedBaseAddress='1' DataExecutionPrevention='1' ProgramDatabaseFile")
    
    print ("...done qmaking")
    return os.path.exists(pro_file+"."+PROJ_EXT)
        

def qmake_mac(pro_file, QMAKE_CONFIG, QMAKESPEC, QTDIR, RELEASE_SUFFIX="", QMAKEFLAGS="", APP_NAME="", CLEAN=True, CLEAN_ONLY=False):
    sdk = {
        "QTDIR" : QTDIR,
        "QMAKESPEC" : QMAKESPEC,
        "PATH" : "$PATH:" + QTDIR + "/bin"
    }

    rootdir = ""
    if len(os.path.dirname(pro_file))>0:
        rootdir = os.path.dirname(pro_file) + "/"
    proname = os.path.basename(pro_file)

    if len(APP_NAME)==0:
        APP_NAME = proname.replace(".pro","")
    APP = APP_NAME+RELEASE_SUFFIX

        
    # ------------------------------------
    # clean
    if CLEAN:
        print ("Clean'ing "+QMAKE_CONFIG+" version...")
    
        for fd in [APP+".build", rootdir+APP+".xcodeproj", "Release"+RELEASE_SUFFIX+"/"+APP_NAME+".app", rootdir+"Release/"+APP_NAME+".app", 
                "Release/"+APP_NAME+".app", rootdir+"Release/"+APP_NAME+".app.dSYM", rootdir+"tmp", "moc_*.cpp", "qt_makeqmake.mak", "qt_preprocess.mak", "project.pbxproj" ]:
            if os.path.isdir(fd):
                shutil.rmtree(fd, ignore_errors=True)
            else:
                for fl in glob.glob(fd):
                    os.remove(fl)
    
    if CLEAN_ONLY:
        return True
    # qmake
    cdir = os.getcwd()
    if len(rootdir)>0:
        os.chdir(rootdir)
    print ("Qmake'ing "+QMAKE_CONFIG+" version...")
    shcall_mac(
        'qmake ' + QMAKEFLAGS + ' ' + proname + ' -spec ' + QMAKESPEC + ' "CONFIG+=' + QMAKE_CONFIG + '" -o ./' + APP + '.xcodeproj'
        , sdk
    )
    if len(rootdir)>0:
        os.chdir(cdir)
    
    print ("...done")
    return os.path.exists( rootdir+APP+".xcodeproj")
    
    
def BUILD2(pro_file, QMAKESPEC="", QTDIR="", RELEASE_SUFFIX="", DESTDIR="./release", APP_NAME=""):

    sdk_json = get_sdk()
    if APP_NAME=="":
        APP_NAME = getValue(pro_file, 'TARGET\\s*=\\s*([^\\s]+)\\s*$')
        if APP_NAME=="":
            proname = os.path.basename(pro_file)
            APP_NAME = proname.replace(".pro","")
    if QMAKESPEC=="":
        QMAKESPEC = sdk_json["QMAKESPEC"]
    if QTDIR=="":
        QTDIR = sdk_json["QTDIR"]
    DESTDIR=DESTDIR.replace("./", os.path.dirname(pro_file)+"/")
    
    if os.name=="nt":
        return build_vs(pro_file, QMAKESPEC, QTDIR, DESTDIR, APP_NAME)
    else:
        return build_xcode_mac2(pro_file, QMAKESPEC, QTDIR, RELEASE_SUFFIX, DESTDIR, APP_NAME)
        
def build_vs(pro_file, QMAKESPEC, QTDIR, DESTDIR, APP_NAME):
    QTDIR=QTDIR.replace("/","\\")
    sdk = {
        "QTDIR":QTDIR,
        "QMAKESPEC":QMAKESPEC,
        "PATH":"%PATH%;" + QTDIR + "\\bin"
    }
        
    # build
    VSCOMNTOOL = 'call "%'+VSCOMNTOOLS[QMAKESPEC]+'%vsvars32.bat"\n'
    PROJ_EXT = "vcproj" if QMAKESPEC=="win32-msvc2008" else "vcxproj"

    print ("Building...")
    dest = DESTDIR+"/" + APP_NAME+".exe"
    if os.path.exists(dest):
        try:
            os.remove(dest)
        except Exception as e:
            print ("Unable to remove " + dest), e
            return False

    shcall(
        VSCOMNTOOL
        +"msbuild /clp:ErrorsOnly "+pro_file+"."+PROJ_EXT+" /t:Rebuild /property:Configuration=Release  /verbosity:quiet"
        , sdk,
        log = LOG
    )

    
    if not os.path.exists(DESTDIR+"\\" + APP_NAME+".exe"):
            error_report()
            print ("Build Failed!")
            return False
    
    print ("... Build Ok!")
    return True


def build_xcode_mac2(pro_file, QMAKESPEC, QTDIR, RELEASE_SUFFIX, DESTDIR, APP_NAME):

    APP = APP_NAME + RELEASE_SUFFIX
    sdk = {
        "QTDIR" : QTDIR,
        "QMAKESPEC" : QMAKESPEC,
        "PATH" : "$PATH:" + QTDIR + "/bin",
    }
    # ------------------------------------	
    
    print ("Building "+RELEASE_SUFFIX+" version...")
    
    if os.path.exists(DESTDIR+"/" +APP_NAME+".app"):
        shutil.rmtree(DESTDIR+"/" +APP_NAME+".app", ignore_errors=True)
    if not os.path.exists(DESTDIR):
        os.makedirs(DESTDIR)
    
    rootdir = ""
    if len(os.path.dirname(pro_file))>0:
        rootdir = os.path.dirname(pro_file) + "/"
        
    cdir = os.getcwd()
    if len(rootdir)>0:
        os.chdir(rootdir)
    shcall_mac(
        "xcodebuild -project ./" + APP + ".xcodeproj -configuration Release"
        , sdk
    )
    if len(rootdir)>0:
        os.chdir(cdir)
    
    # on macos, unlike win, build result saved only to pro-file folder
    if len(rootdir)>0:
        shutil.copytree(rootdir + "Release/" +APP_NAME+".app", DESTDIR+"/" +APP_NAME+".app")
    
    # output error
    if not os.path.exists(DESTDIR+"/" +APP_NAME+".app/Contents/MacOS/"+APP_NAME):
        error_report()
        return False
    
    print ("...build OK!")
    return True


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def error_report():
    with open(LOG_FILE) as f:
        lines = 0
        for line in f:
            if line.find("error:")<0 and line.find(": error")<0 and lines<1:
                continue
                
            if line.find("error:")>=0 or line.find(": error")>=0:
                lines=4 if os.name=="nt" else 1
            if not os.name=="nt":
                line = bcolors.FAIL + line + bcolors.ENDC
            print (line)
            lines = lines - 1
        f.closed

def log_message(message):
    with open(LOG_FILE, "a") as f:
        f.write(message)
        f.close()
    return

def log_clean():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

#------------------------------- DEPENDENCES


def check_deps(deps, projects=[], folder="tools"):
    print("Checking depens..."),
    for dep in deps:
        if dep in projects:
            cDep = projects[dep]
        elif dep in DEPS:
            cDep = DEPS[dep]
        else:
            print ("Error: no dependence found: " + dep)
            quit(code=2) # no dep found
        
        if not prepare_pkg(cDep, folder + "/" + dep):
            quit(code=1) # dep was not build
    print("...done")
    return



#-------------------------------- INSTALLERS
def find_innosetup():
    prgfiles = os.environ["ProgramFiles(x86)" if "ProgramFiles(x86)" in os.environ else "ProgramFiles"]
    if os.path.exists(prgfiles + "\\Inno Setup 5\\ISCC.exe"):
        return prgfiles + "\\Inno Setup 5\\ISCC.exe"
    return ""
    
def find_asprotect():
    prgfiles = "ProgramFiles(x86)" if "ProgramFiles(x86)" in os.environ else "ProgramFiles"
    if os.path.exists(os.environ[prgfiles] + "\\ASProtect 1.35 Release\\ASProtect.exe"):
        return "%" + prgfiles + "%\\ASProtect 1.35 Release\\ASProtect.exe"
    return ""

# output - installer file name == OutputBaseFilename param in innosetup
def innosetup(iss, output=""):
    print("Creating iis setup..."),
    cmd = '"' + find_innosetup() + '"' + ((' /F' + output + '') if output else "")  + ' /Q ' + iss.replace("/","\\")
    res = os.system(cmd)
    print("ok" if res==0 else "fail")
    return res==0
    
def asrpotect(aspr):
    print("ASProtect'ing..."),
    res = CALL_WRAP('"%asprotect%" -process "' + os.path.abspath(aspr) + '"', {
        "asprotect" : find_asprotect()
    })["status"]
    print("ok" if res==0 else "fail")
    return res==0
    
def getArgs():
    params={}
    for arg in sys.argv[1:]:
        if arg[0]=="-": 
            arg=arg[1:]
            
        param = arg.split("=")
        if len(param)>1:
            params[param[0]]=param[1]
        else:
            params[arg]=True
    return params

# ---------- META
# http://dl.google.com/closure-compiler/compiler-latest.zip
def jso(list, src_dir="", dest_dir="", header=True):
    files = getFile(list).splitlines()
    for fname in files:
        fname = fname.strip()
        if len(fname)>0:
            print "jso: " + fname
            jso_call(src_dir + fname, dest_dir + fname, header)
            # CALL('java -jar "tools/compiler.jar" --language_in ECMASCRIPT5 "' + src_dir + fname + '" --js_output_file="' + dest_dir + fname + '"')
    return


def first_comment(path):
    data = getFile(path)
    p = re.compile("^((\\s*/\\*([^*]|(\\*+([^*/])))*\\*+/)|(\\s*//[^\\n\\r]*))*", re.MULTILINE|re.DOTALL)
    m = p.match(data)
    if (m):
        return m.group(0)
    return ""
    
# @return 0 - OK
# @return -1 - file not exixts
# @return other - error
def jso_call(src_file, dest_file="", header=True):
    if (dest_file==""):
        dest_file = src_file
        
    if not os.path.exists(src_file):
        return -1
    
    # work with tmp-file if dest_file==src_file
    f_tmp_path=""
    if dest_file == src_file:
        f_out = tempfile.NamedTemporaryFile(suffix='.out', prefix='tmp', delete=False) #register tmp
        f_tmp_path = f_out.name
        f_out.close() # later work only with f_out_path
        dest_file = f_tmp_path
    
    comment = first_comment(src_file)
    res = CALL_WRAP('java -jar "tools/compiler.jar" --warning_level=QUIET --language_in ECMASCRIPT5 "' + src_file + '" --js_output_file="' + dest_file + '"' )
    # if need header
    if (header):
        writeFile(dest_file, comment + "\n" + getFile(dest_file))
        
    if f_tmp_path != "": # dest==src
        shutil.copyfile(f_tmp_path, src_file)
        os.remove(f_tmp_path)

    return res


# http://dl.google.com/closure-compiler/compiler-latest.zip
def yuicompressor(list, header, src_dir, dest_dir=""):
    print ("Obfuscating..."),
    if len(dest_dir)==0:
        dest_dir = src_dir
    
    files = getFile(list).splitlines()
    for fname in files:
        fname = fname.strip().replace("\\","/")
        if len(fname)>0:
            shutil.copyfile(header, dest_dir + "/" + fname+".tmp")
            CALL_WRAP('java -jar "package/yuicompressor-2.4.6.jar" "' + src_dir + "/" + fname + '" >> "' + dest_dir + "/" + fname + '.tmp"')
            
            if os.path.exists(dest_dir + "/" + fname):
                os.remove(dest_dir + "/" + fname)
            os.rename(dest_dir + "/" + fname + '.tmp', dest_dir + "/" + fname)
    
    print ("down")	
    return


# copy lang files with remove lines code and so on
def languages(langs, RES_PATH, QTDIR):
    print ("Copy languages..."),
    if not os.path.exists(RES_PATH+"/language"):
        os.makedirs(RES_PATH+"/language")
    
    for file in glob.glob(langs):
        CALL_WRAP(QTDIR + '/bin/lconvert --no-obsolete --locations none --no-ui-lines -i "'+file+'" -o "' + RES_PATH + '/language/' + os.path.basename(file)+'"')
    print ("done")

# update language files by code, run it time to time
def lupdate(pro, QTDIR):
    print ("Update languages..."),
    CALL_WRAP(QTDIR + '/bin/lupdate '+pro)
    print ("done")

    
#  ---------- INSTALERS
# Make DMG
# now start only from package/macos
def makedmg(VAR_APP_NAME, VAR_PKG_PATH, VAR_DMG_FILE, pkgfiles):
    
    #srcApplication = VAR_PKG_PATH + "/" + VAR_APP_NAME + ".app"
    #--------
    backgroundPictureName="bg03.png"
    
    # prepare tmp folder
    #if os.path.isdir(VAR_PKG_PATH):
    #	shutil.rmtree(VAR_PKG_PATH)
    #os.mkdir(VAR_PKG_PATH)
    
    distutils.dir_util.copy_tree(pkgfiles+"/.background", VAR_PKG_PATH+"/.background") 
    distutils.file_util.copy_file(pkgfiles+"/.DS_Store", VAR_PKG_PATH+"/.DS_Store") 
    
    #distutils.dir_util.copy_tree(srcApplication, VAR_PKG_PATH+"/" + VAR_APP_NAME + ".app") 
    
    # create applications link
    os.symlink("/Applications", VAR_PKG_PATH + "/Applications")
    
    
    #create tempary dmg
    if os.path.exists(VAR_DMG_FILE+".temp.dmg"):
        os.remove(VAR_DMG_FILE+".temp.dmg")
    
    mkdmg_script = """
    title="${VAR_APP_NAME}"
    hdiutil create -srcfolder "${VAR_PKG_PATH}/" -volname "${VAR_APP_NAME}" -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDRW "${VAR_DMG_FILE}.temp.dmg"
    
    #Mount the disk image, and store the device name (you might want to use sleep for a few seconds after this operation)
    device=$(hdiutil attach -readwrite -noverify -noautoopen "${VAR_DMG_FILE}.temp.dmg" | egrep '^/dev/' | sed 1q | awk '{print $1}')
    
    # wake-up system before script run
    caffeinate -u&
    sleep 2
    killall caffeinate
    
    # Use AppleScript to set the visual styles (name of .app must be in bash variable "VAR_APP_NAME", use variables for the other properties as needed):
    applicationsLink="Applications"
    echo '
    tell application "Finder"
    tell disk "'${VAR_APP_NAME}'"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {400, 100, 885, 330}
    set theViewOptions to the icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 128
    set background picture of theViewOptions to file ".background:'${backgroundPictureName}'"
    #make new alias file at container window to POSIX file "/Applications" with properties {name:"Applications"}
    #delay 5
    # pos of VAR_APP_NAME
    set position of item "'${VAR_APP_NAME}'" of container window to {136, 120}
    set position of item "Applications" of container window to {373, 130}
    # pos of applications link
    set position of item "'${applicationsLink}'" of container window to {373, 115}
    update without registering applications
    delay 5
    eject
    end tell
    end tell
    ' | osascript
    
    #open pack.temp.dmg
    
    # Finialize the DMG by setting permissions properly, compressing and releasing it:
    #chmod -Rf go-w /Volumes/"${title}"
    #sync
    #sync
    #hdiutil detach ${device}
    rm -f "${VAR_DMG_FILE}"
    hdiutil convert "${VAR_DMG_FILE}.temp.dmg" -format UDZO -imagekey zlib-level=9 -o "${VAR_DMG_FILE}"
    """
    mkdmg_script = mkdmg_script.replace('${VAR_APP_NAME}',VAR_APP_NAME)
    mkdmg_script = mkdmg_script.replace('${VAR_DMG_FILE}',VAR_DMG_FILE)
    mkdmg_script = mkdmg_script.replace('${VAR_PKG_PATH}',VAR_PKG_PATH)
    mkdmg_script = mkdmg_script.replace('${backgroundPictureName}',backgroundPictureName)

    os.system(mkdmg_script)
    
    if os.path.exists(VAR_DMG_FILE+".temp.dmg"):
        os.remove(VAR_DMG_FILE+".temp.dmg")

    
# run macdeployqt
# files2remove - List of files or directoies for remove from bundle, format: <file/dir name>[^<except filenames list separated by ; >]
def macdeployqt(QTDIR,outBundle,files2remove):
    ''' prepare bundle, copy all using frameworks and remove shown files '''
    
    # Check files and paths 
    if not os.path.exists(QTDIR) or not os.path.isdir(QTDIR):
        print("Incorrect path to Qt")
        return 1

    # Copy Qt libs for create independent app
    print("\nDeploying Qt to .app bundle...")
    os.system(QTDIR + "/bin/macdeployqt " + outBundle)
    print("...done deploing\n")

    #remove some unusable libs
    for item in files2remove:
        path = item.split("^")[0]
        if os.path.isdir(outBundle+"/" + path):
            if len(item.split("^")) > 1:
                exceptList = item.split("^")[1].split(";")
                libs = glob.glob(outBundle+"/" + path+"/*.dylib")
                for lib in libs:
                    if os.path.basename(lib) not in exceptList:
                        os.remove(lib)
            else:
                shutil.rmtree(outBundle+"/" + path, ignore_errors=True)
        else:
            del_files = glob.glob(outBundle+"/" + path)
            for del_file in del_files:
                os.remove(del_file)
    
    
frameworksDir = "/Contents/Frameworks/"
def deploy_fix(QTDIR, outBundle):
    '''fix deploy app'''
    # Copy and patch plists for frameworks (it's fix macdeployqt bug)
    QtVer = getQtVersion(QTDIR)
    if len(QtVer)==0:
        QtVer = "5.3.0"
    QtVerMajor = QtVer[0]
    
    frameworks = os.listdir(outBundle+frameworksDir)
    for framework in frameworks:
        frameworkDir = outBundle+frameworksDir+framework
        if not os.path.isdir(frameworkDir):
            continue
        
        if not os.path.exists(frameworkDir+"/Versions/"+QtVerMajor+"/Resources"):
            os.makedirs(frameworkDir+"/Versions/"+QtVerMajor+"/Resources")
            
        # info.plist
        #shutil.copy(QTDIR+"lib/"+framework+"/Contents/Info.plist", frameworkDir+"/Versions/5/Resources/")
        fwname = framework[:framework.index(".")]
        if not os.path.isfile(QTDIR+"/lib/"+framework+"/Contents/Info.plist"):
            continue
        plist = open(QTDIR+"/lib/"+framework+"/Contents/Info.plist","rt")
        content = []
        for line in plist.readlines():
            line = line.rstrip()
            line = line.replace("QtPositioning_debug","QtPositioning") # fixed wrong info for sign
            line = line.replace("QtPrintSupport_debug","QtPrintSupport") # fixed wrong info for sign
            line = line.replace("QtQml_debug","QtQml") # fixed wrong info for sign
            line = line.replace("QtQuick_debug","QtQuick") # fixed wrong info for sign
            content.append(line)
        plist.close()
        
        pos = content.index("</dict>")
        content.insert(pos, "\t<string>" + QtVer + "</string>")
        content.insert(pos, "\t<key>CFBundleVersion</key>")
        content.insert(pos, "\t<string>org.qt-project."+fwname+"</string>")
        content.insert(pos, "\t<key>CFBundleIdentifier</key>")

        plist_out = open(frameworkDir+"/Versions/" + QtVerMajor + "/Resources/Info.plist", "w")
        plist_out.write("\n".join(content))
        plist_out.close()
        
        # additional symlinks
        if os.path.exists(frameworkDir+"/Resources"):
            shutil.rmtree(frameworkDir+"/Resources")
        os.symlink(QtVerMajor, frameworkDir+"/Versions/Current")
        os.symlink("Versions/Current/Resources",frameworkDir+"/Resources")
        os.symlink("Versions/Current/"+fwname, frameworkDir+"/"+fwname)


def sign_mac3(outBundle, devName, entitlements=""):
    '''create singined package'''

    if len(entitlements)>0:
        if not os.path.exists(entitlements) or os.path.isdir(entitlements):
            print("Entitlements file not found")
            exit()
        entitlements = '--entitlements ' + entitlements
    
    # Sign app
    res = os.system('codesign -f --deep '+entitlements+' -s "'+devName+'" '+outBundle)
    if (res == 0):
        print("ok!")
    else:
        print("fail!")
        return False
        print("if you using ssh try to unlock it")

    print("\nCheck signing:")
    os.system('codesign --verify --verbose=4 '+outBundle)
    
    return True

    
def mac_pkg(appName, outBundle, pkgsign, output):
    print("\nBuilding package...")
    res = os.system('productbuild --component "'+outBundle+'" /Applications --sign "'+pkgsign+'" --product "'+outBundle+'/Contents/Info.plist" '+output)

    if (res == 0 and os.path.exists(output)):
        print("...done. Ok\n")
    else:
        print("...fail :(\n")
        return 2

    print('\nFor test install, run follow command: sudo installer -store -pkg '+output+' -target /')
    print("for submit run \"Application Loader\"")
    print("> open /Applications/Xcode.app/Contents/Applications/Application\\ Loader.app/Contents/MacOS/Application Loader")
    
    print('and select '+output)
    return 0

    
    

# @file
# @libs=[...]
reNAME = re.compile("^(?:.*[\\/])?([^\\.\\/]*)[\\.]([^\\/]*)$")
def install_name_tool(file, lib):
    m = reNAME.search(lib)
    
    if not m:
        return
    lib_name = m.group(1)
    
    for file_lib in otool(file):
        file_lib_name=reNAME.search(file_lib)
        
        if file.endswith("libicuuc.55.dylib"):
            print ("file_lib = "+file_lib + str(file_lib.endswith(lib_name)))
            print (file_lib_name)
        
        if not file_lib_name:
            continue
        if file_lib_name.group(1)==lib_name and (file_lib != lib):
            if file.find(lib_name)>=0:
                CALL_WRAP("install_name_tool -id \"" +lib + "\" \"" + file + "\"")
            else:
                CALL_WRAP("install_name_tool -change \"" + file_lib + "\" \"" +lib + "\" \"" + file + "\"")
    
def install_name_tool_multi(files, libs):
    for file in files:
        for lib in libs:
            install_name_tool(file, lib)

def otool(file):
    libs = []
    cmd = CALL_WRAP("otool -L "+file)["message"]
    p = re.compile("^\\s+([^\\s][^()]*[^\\s])\\s+\\(.*\\)")
    for line in cmd.split("\n"):
        m = p.search(line)
        if m:
            value = m.group(1)
            libs.append(value)
            
    return libs
    
def unlock(password=""):
    '''unlock keychain for ssh-terminal for using this script'''
    if password:
        password = " -p " + password
    os.system('security -v unlock-keychain' + password+' "/Users/'+os.getlogin()+'/Library/Keychains/login.keychain"')

    
gradlew = "gradlew.bat" if os.name=="nt" else "./gradlew"
def gradle(root, result, echo = True):

    # start 
    cdir = os.getcwd();
    os.chdir(root)
    os.system(gradlew + " assembleRelease")
    os.chdir(cdir)
    
    result = root+"/"+result
    if echo:
        if not os.path.exists(result):
            print ("Builfd fail!!")
            return ""
        else:
            print ("Created package: " + result)
            
    return result


def os_copy(src, dest):
    if sys.platform == "win32": # python copy
        if not os.path.isdir(src):
            if not os.path.exists(os.path.dirname(dest)):
                os.makedirs(os.path.dirname(dest))
            shutil.copy(src, dest)
        else:
            shutil.copytree(src, dest)
    else:
        os.system('cp -Rf "'+ src + '" "' + dest + '"')

    return;


def getZip7():
    zip7 = os.environ["ProgramFiles"] + "\\7-Zip\\7z.exe"
    if not os.path.exists(zip7):
        zip7 = os.environ["ProgramFiles(x86)"] + "\\7-Zip\\7z.exe"
        if not os.path.exists(zip7):
            return ""
    return '"' + zip7 + '"'


# call system zip 
# @param zip - name result zip
# @param dir - dir to zip
def os_zip(zip, dir):
    zip = os.path.abspath(zip)
    dir = os.path.abspath(dir)
    if os.name=="nt":
        res = CALL_WRAP(getZip7() + ' a "' + zip + '" "' + dir + '\\*"')
    else:
        cdir = os.getcwd()
        try:
            os.chdir(dir)
            res = CALL_WRAP('zip -r9 "' + zip + '" ./')
        finally:
            os.chdir(cdir)
        
    return not res["status"]
    
    
# call system zip 
# @param zip - name result zip
# @param dir - dir to zip
def os_unzip(zip, dir=""):
    zip = os.path.abspath(zip)
    if not dir:
        dir = os.path.dirname(zip)
    else:
        dir = os.path.abspath(dir)
    if os.name=="nt":
        res = CALL_WRAP(getZip7() + ' x "' + zip + '" -o"' + dir + '\\"')
    else:
        res = CALL_WRAP('unzip "' + zip + '" -d "' + dir + '"')
        
    return not res["status"]

    
def zip(zipname, file):
    print ("zipping " + file + " to " + zipname)
    if os.path.exists(zipname):
        os.remove(zipname)
    myzip = zipfile.ZipFile(zipname,'w')
    
    file = os.path.abspath(file)
    cdir = os.getcwd()
    try:
        if os.path.isfile(file):
            os.chdir(os.path.dirname(file))
            
            myzip.write(os.path.basename(file))
        else:
            os.chdir(file)
            for root,dirs,files in os.walk("./"):
                for name in files:
                    myzip.write(os.path.join(root, name).replace("\\","/"))
    finally:
        os.chdir(cdir) # revert current dir
    
    myzip.close()


# extracting archive to dir of archive-file
def unzip(fname, fdir=""):
    fname = os.path.abspath(fname)
    if fdir=="":
        fdir = os.path.dirname(fname)
    
    # extracting to tmp
    print ("extracting " + fname + " ...")
    try:
        ar = zipfile.ZipFile(fname)
        ar.extractall(fdir)
        ar.close()
    except:
        print("Error archive extracting " + fname)
        return False
    
    return True


# note: if are not using ip of server, for local domain use ".local" suffix for compatability with macos 
# @param {Path} netpath - network path to server + share, ex: "//Server/Share", may by with path, ex: "//Server/Share/Path"
# @param {Path} point - point mount to, folder for *nix "~/Server" and volume label for win "M:"
# @return {Path} moint point
MTAB = {} # {server: mountPoint}
REG_NETPATH = '^//([^\\/]+)/([^\\/]+)(?:/(.*))?$'
def smb_mount(netpath, point = ""):
    # extract server name from path and netpath
    netserver = ""
    m = re.search(REG_NETPATH, netpath)
    if m:
        netserver = "//" + m.group(1) + "/" + m.group(2)
        if not point:
            point = "~/" + m.group(1) + "_" + m.group(2) + "_share"
        netpath = m.group(3)
    else:
        return netpath
    
    
    # retrun if allready mounted
    if netserver in MTAB:
        return MTAB[netserver] + ("/" + netpath if netpath else "")

    if sys.platform == 'darwin':
        if point == "":
            point = "~/Server"
        point = os.path.expanduser(point)
        if not os.path.exists(point):
            os.makedirs(point)
        os.system('mount_smbfs -N ' + netserver.replace("//","//guest:@") + ' ' + point) # using guest for mac sharing

    elif sys.platform == "win32":
        if point=="" or len(point)>2:
            DRIVES = ['H:', 'I:', 'J:', 'K:', 'L:', 'M:', 'N:', 'O:', 'P:', 'Q:', 'R:', 'S:', 'T:', 'U:', 'V:', 'W:', 'X:', 'Y:', 'Z:'] # possible drives
            busy = getCmdValue("fsutil fsinfo drives","((?:\w+\:\\\\\s*)+)").replace("\\","").split(" ") # getdrive lists - busy drives
            for point in (set(DRIVES) - set(busy)):
                break
            
        cmd = 'net use ' + point + " " + netserver.replace(".local","").replace("/","\\")
        print cmd
        if os.system(cmd) != 0: # mount error
            return netserver + ("/" + netpath if netpath else "")
        
    else:
        print "Error platform " + sys.platform + " is not supported"
        return ""
        
    MTAB[netserver] = point # save
    return point + ("/" + netpath if netpath else "")


# umount point if registered  
# point may be not mounted
# @param point - may be with path, if null then umount all points
def smb_umount(point):
    point = point.replace("/","").replace("\\","")
    
    # if no point then umount all points
    if not point:
        res = True
        for p in MTAB.values():
            res = res and smb_umount(p)
        return res
    
    # remove path from point
    netpath = ""
    for key,val in MTAB.items():
        if point.startswith(val):
            point = val
            netpath = key
    
    # pass if point is no mounted
    if not point in MTAB.values():
        return True
    
    if sys.platform == 'darwin':
        os.system('umount ' + point)
        os.rmdir(point)
    elif sys.platform == "win32":
        os.system('net use ' + point + ' /Delete')
    else:
        print "Error platform " + sys.platform + " is not supported"
        return False
    
    MTAB.pop(netpath, None) # remove point
    
    return True


def net_copy(file, netpath):
    if not os.name=="nt":
        return os.system('rsync -avz '+file + ' ' + netpath)
    else:
        return os.system('xcopy /Y ' + file.replace("/","\\") + ' ' + netpath.replace("/","\\")+"\\")


def smb_copy(in_file, out_file):
    # connect to in
    in_point = ""
    in_path = in_file
    m = re.search(REG_NETPATH, in_file)
    if m:
        in_point = smb_mount("//" + m.group(1) + "/" + m.group(2)) + "/"
        in_path = m.group(3)
    
    # connect to out
    out_point = ""
    out_path = out_file
    m = re.search(REG_NETPATH, out_file)
    if m:
        out_point = smb_mount("//" + m.group(1) + "/" + m.group(2)) + "/"
        out_path = m.group(3)
        
    # copy
    res = 1
    try:
        try:
            print (in_point + in_path, out_point + out_path)
            res = shutil.copy(in_point + in_path, out_point + out_path)
        except:
            pass
    finally:
        if len(in_point)>0:
            smb_umount(in_point)
        if len(out_point)>0:
            smb_umount(out_point)
    
    return (not res)


# using for get params for 
# ex: getValue("src/settings.h", 'APP_VERSION\s+\\"([^\\"]+)\\"')
def getValue(file, reg_value):
    f = open(file,"rt")
    value =""
    p = re.compile(reg_value)

    for line in f.readlines():
        m = p.search(line)
        if m:
            value = m.group(1)
            break

    f.close()
    return value

    
def getQtVersion(QTDIR):
    qmake = QTDIR + '/bin/qmake'
    if os.name=="nt":
        qmake = qmake.replace("/","\\") # forwin
        qmake += ".exe"
        
        
    if not os.path.exists(qmake):
        return ""
        
    qmake += ' -v'
    lines = CALL_WRAP(qmake)["message"].split("\n")
    p = re.compile("version\\s+(\\d+[\\.]\\d+[\\.]\\d+)") 
    
    value = ""
    for line in lines:
        m = p.search(line)
        if m:
            value = m.group(1)
            break
    return value

    
def getCmdValue(cmd, regstr="(.*)"):
    lines = CALL_SDK3(cmd)["message"].split("\n")
    p = re.compile(regstr) 
    
    value = ""
    for line in lines:
        m = p.search(line)
        if m:
            value = m.group(1)
            break
    return value
    
    
# Wrapping command call
# Note: batch files has condition for escaping, ex. for win use %% instead % in double quoted strings
# All paths using with /
# PATH enviroment var use ; as separator
# 		and replace %PATH% -> $PATH
# note: debug mode pass temp bat-files in %temp% dir
# @param {String[String]} addEnv
# @param {Bool} sys_adopt - adopting script to sys-call: replace paths, convert PATH enviroment
# @param {String} runpath - path run from
# @return {Object} res
# @return {Object} res.status - os exit status code, ex: win: 0-success, 1-error; mac:0-success, <int>-exit status
# @return {Object} res.message - command result message
def CALL_WRAP(cmds, addEnv={}, sys_adopt=True, runpath=""):

    # create temporary output log-message file
    f_out = tempfile.NamedTemporaryFile(suffix='.out', prefix='tmp', delete=False)
    f_out_path = f_out.name
    
    if sys_adopt and os.name=="nt":
        f_out_path = f_out_path.replace("/","\\") # for win
    f_out.close() # later work only with f_out_path

    # adopt path to system
    if sys_adopt and "PATH" in addEnv:
        if os.name=="nt":
            addEnv["PATH"] = addEnv["PATH"].replace("/","\\")
        else:
            addEnv["PATH"] = addEnv["PATH"].replace(";",":").replace("%PATH%", "$PATH")

    # wraping shell-script
    f_cmd = tempfile.NamedTemporaryFile(suffix='.cmd', prefix='tmp', delete=False)
    f_cmd_path = f_cmd.name
    if sys_adopt and os.name=="nt":
        f_cmd_path = f_cmd_path.replace("/","\\")	
    
    cdir = os.getcwd()
    if runpath:
        os.chdir(runpath)
    status = 0
    try:
        # os-dependend call
        if os.name=="nt":
            if not DEBUG:
                f_cmd.write("@echo off\n")
            for v in addEnv:
                f_cmd.write("set " + v + "=" + addEnv[v] + "\n")
            f_cmd.write(cmds)
            f_cmd.close()
            
            try:
                status = os.system("call " + f_cmd_path + " >> " + f_out_path)
            except Exception as e:
                status = 1
        
        else:
            if DEBUG:
                f_cmd.write("set -v off\n")
            for v in addEnv:
                f_cmd.write("export " + v + "=" + addEnv[v]+"\n")
            f_cmd.write(cmds + "\n")
            f_cmd.close()
            
            os.chmod(f_cmd_path, stat.S_IXUSR | stat.S_IRUSR | stat.S_IXGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH)
            try:
                status = os.system('"' + f_cmd_path + '" >> "' + f_out_path + '"')
            except Exception as e:
                status = 1
    finally:
        os.chdir(cdir)
        
    if not DEBUG:
        os.remove(f_cmd_path)
    else:
        print "cmd:" +f_cmd_path

    # read output message	
    message = getFile(f_out_path);
    if not DEBUG:
        os.remove(f_out_path)
    
    # prepare log
    if LOG:
        log_message(cmds + "\n" + message)
    
    result = {}
    result["status"] = status
    result["message"] = message
    
    return result

def check_brew():
    if CALL_WRAP("brew --version")["message"].find("Homebrew") < 0:
        print ("Homebrew was not installed")
        print ("Try to install with:")
        print ('/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"')
        quit(1)
        
    return True

# get curl path to run
# C:\Program Files\Git\usr\bin\curl.exe
def get_curl():
    sdk = get_sdk()
    curl = ""
        
    # get from sdk
    if "curl" in sdk:
        curl = sdk["curl"]
    
    # check curl and calc if need
    if len(curl)==0 or CALL_WRAP(curl + " --version")["message"].find("curl") < 0:
        # init general curl
        curl = "curl"
        
        if CALL_WRAP(curl + " --version")["message"].find("curl") < 0:
            # get from git installation
            gitdir = os.path.dirname(CALL_WRAP("where git" if os.name=="nt" else "which git")["message"])
            curl = '"' + os.path.abspath(gitdir + "/../usr/bin/curl.exe") + '"'
            if os.name=="nt":
                curl = curl.replace("/","\\")
            
            if CALL_WRAP(curl + " --version")["message"].find("curl") < 0:
                print "Can't find curl, please install it"
                quit(1)
                
        set_sdk_param("curl", curl)
        
    return curl

    

# curl -i -X POST -H "Content-Type: multipart/form-data" 
# -F "file=@addon.zip" http://my.domain.com/
def curl2(url, metod="GET", binary="", file="", headers={}, add = ""):
    cmd = get_curl()
    cmd += " " +add
    cmd += " -X " + metod
    if len(binary)>0:
        cmd += ' --data-binary "@' + binary + '"'
    for h in headers:
        cmd += ' --header "' + h +": " + headers[h] + '"'
    if len(file)>0:
        cmd += ' -F "file=@' + file + '"'
    cmd += " " + url
    
    res = CALL_WRAP(cmd)
    return res["message"]


def jsdoc(path):
    sdk = get_sdk()
    jsdoc = ""
    if "jsdoc" in sdk:
        jsdoc = sdk["jsdoc"]

    # check jsdoc 
    if len(jsdoc)==0 or CALL_WRAP(jsdoc + " -v")["message"].find("JSDoc") < 0:
        # init jsdoc
        jsdoc = "jsdoc"
        if CALL_WRAP(jsdoc + " -v")["message"].find("JSDoc") < 0:
            jsdoc = "node_modules/.bin/jsdoc"
            if os.name=="nt":
                jsdoc = jsdoc.replace("/","\\")
                
            if CALL_WRAP(jsdoc + " -v")["message"].find("JSDoc") < 0:
                print ("Can't find jsdoc, please install it with:")
                print ("> npm install jsdoc")
                raise SystemExit
                quit()

        set_sdk_param("jsdoc", jsdoc)
    
    os.system(jsdoc + " -c " + path)

    return True
    
    
# @return { mkspec: [{ "QTDIR":qtdir, "MKSPEC" : mkspec, "version": version }] }
def findQt():
    
    if sys.platform == 'win32':
        # calc qt install dir by qtcreator.exe installation
        Qt = getCmdValue(
            "reg query HKEY_CLASSES_ROOT\Applications\qtcreator.exe\shell\open\command", 
            '\\(Default\\)\\s+REG_SZ\\s+\\"([^"]+)\\\\Tools\\\\QtCreator\\\\bin\\\\qtcreator.exe\\"')
        
        
        if (Qt==""):
            Qt = getCmdValue(
                "reg query HKEY_CLASSES_ROOT\Applications\QtProject.QtCreator.pro\shell\Open\Command", # check for qtcreator 4.0.3
                '\\(Default\\)\\s+REG_SZ\\s+([^"]+)[\\\\]+Tools[\\\\]+QtCreator[\\\\]+bin[\\\\]+qtcreator.exe')
                
        Qt = Qt.replace("\\","/")
    else:
        Qt = "/Developer/Qt"

    qtdirs={}
    if (len(Qt)==0 or not os.path.exists(Qt)):
        return qtdirs
    
    if (Qt[len(Qt)-1] != "/"):
        Qt += "/"
    
    reVer = re.compile("^[\\d\\.]+$")
    reMkSpec = re.compile("^([^_]+)")
    
    
    # versions folders
    for ver in os.listdir(Qt):
        if not os.path.isdir(Qt + ver):
            continue
        if not reVer.search(ver):
            continue
        
        # mkspecs folders
        for ms in os.listdir(Qt + ver):
            # has qmake
            qtdir = Qt + ver + "/" + ms
            
            # valid qmake
            version = getQtVersion(qtdir)
            if len(version)==0:
                continue
            
            # valid MkSpec
            m = reMkSpec.search(ms)
            if not m:
                continue
            if sys.platform == 'win32':
                mkspec = "win32-" + m.group(1)
            else:
                mkspec = "macx-" + m.group(1)
            
            
            # save
            if not mkspec in qtdirs: 
                qtdirs[mkspec] = []
            
            
            info = {
                "QTDIR"  : qtdir,
                "MKSPEC" : mkspec,
                "version": version
            }
            qtdirs[mkspec].append(info)
    
    return qtdirs	
    



def parseInt(str, def_val=0):
    try:
        return int(float(str))
    except Exception as e:
        return def_val

# (ver1 <=> ver2) -1 0 1
def cmp_ver(ver1,ver2):
    a_ver1 = ver1.split(".")
    a_ver2 = ver2.split(".")

    i=0
    for v1 in a_ver1:
        if i >= len(a_ver2):
            return 1
        v2 = a_ver2[i]

        if (parseInt(v1)>parseInt(v2)):
            return 1
        if (parseInt(v1)<parseInt(v2)):
            return -1

        i = i+1

    if len(a_ver1) == len(a_ver2):
        return 0
    return -1


# return git log from tag before version to HEAD
def git_changes(ver_to):
    # get version list
    tags = CALL_WRAP("git tag")["message"].split("\n")
    tags = sorted(tags, cmp=cmp_ver)

    # check start version
    ver_from = tags[-1]
    if cmp_ver(ver_from, ver_to) >= 0:
        ver_from = tags[-2]

    log = CALL_WRAP('git log --pretty=format:' + ('"%%h,%%an,%%s" ' if os.name=="nt" else '"%h,%an,%s" ') + ver_from + "..")["message"] # escaping for bat-call

    return log

def svn(url, workdir):
    if not os.path.exists(workdir):
        res = os.system("svn checkout " + url + " " + workdir)
    else: 
        res = os.system("svn update -q " + workdir)
    return (res==0)

# rm -rf
# @param {String} path - path of file or folder, or glob pattern
# @return {Boolean} ok status
def rm_rf(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        else:
            for f in glob.glob(path.replace("/", os.sep)):
                if os.path.isdir(f):
                    shutil.rmtree(f, ignore_errors=True)
                elif os.path.isfile(f) or os.path.islink(f):
                    os.remove(f)
        return not os.path.exists(path)
    except:
        return False
        pass

 
def mk_dir_link(name, target):
    try:
        if os.name=="nt":
            subprocess.call(['mklink', "/J" , name.replace("/", os.sep), target.replace("/", os.sep)], shell=True)
        else:
            os.symlink(target, name)
        return True
    except:
        return False
        pass

        
def rm_dir_link(name):
    try:
        if os.name=="nt":
            subprocess.call(['rmdir', name.replace("/", os.sep)], shell=True)
        else:
            os.unlink(name)
        return True
    except:
        return False
        pass


# ---------------------------
# ------- DEPRECATED --------
# ---------------------------


# deprecated use sign_mac3
def sign_mac(appName, outBundle, devName):
    '''create singined package'''

    print("\nSigning bundle..."),
    # Sign app
    res = os.system('codesign -f --deep -s "'+devName+'" '+outBundle)
    if (res == 0):
        print("ok!")
    else:
        print("fail!")
        return 1
        print("if you using ssh try to unlock it")

    print("\nCheck signing:")
    os.system('codesign --display --verbose=4 '+outBundle)
    
    return 0

# deprecated use sign_mac3
def sign_mac2(appName, outBundle, devName, entitlements=""):
    '''create singined package'''

    if len(entitlements)>0:
        if not os.path.exists(entitlements) or os.path.isdir(entitlements):
            print("Entitlements file not found")
            exit()
        entitlements = '--entitlements ' + entitlements
    
    
    print("\nSigning frameworks, dylibs, and binary..."),
    # Sign frameworks
    #os.system('codesign -s "'+devName+'" '+outBundle+frameworksDir+'*')

    # Sign plugins
    #pluginsDir    = outBundle+"/Contents/PlugIns/"
    #pluginGroups = os.listdir(pluginsDir)
    #for group in pluginGroups:
    #	os.system('codesign -s "'+devName+'"  '+pluginsDir+group+"/*")

        
    # Sign app
    res = os.system('codesign -f --deep '+entitlements+' -s "'+devName+'" '+outBundle)
    if (res == 0):
        print("ok!")
    else:
        print("fail!")
        return 1
        print("if you using ssh try to unlock it")

    print("\nCheck signing:")
    os.system('codesign --display --verbose=4 '+outBundle)
    
    return 0



# deprecated	
def zip7(zip,dir):
    print ("deprecated use os_zip() instead")
    CALL_WRAP(getZip7() + ' a "'+os.path.abspath(zip)+'" "'+os.path.abspath(dir)+'\\*"')


# deprecated, use CALL_WRAP()
# path using with /
# PATH enviroment use ; as separator
# and replace %PATH% -> $PATH
# @param {String[String]} addEnv
def CALL(cmds, addEnv={}):
    print("Warning: CALL() is deprecated, use CALL_WRAP() instead")
    if os.name=="nt":
        if "PATH" in addEnv:
            addEnv["PATH"] = addEnv["PATH"].replace("/","\\")
        #cmds = cmds.replace("/","\\") - win commands use right slash
        
        ftmp = tempfile.NamedTemporaryFile(suffix='.cmd', prefix='tmp',delete=False)
        if not DEBUG:
            ftmp.write("@echo off\n")
        for v in addEnv:
            ftmp.write("set " + v + "=" + addEnv[v]+"\n")
        ftmp.write(cmds)
        fname = ftmp.name.replace("/","\\")
        ftmp.close()
        res = os.system("call "+fname + (" >> " + LOG_FILE if LOG else ""))

        if not DEBUG:
            os.remove(fname)		
        return res
        
    else:
        if "PATH" in addEnv:
            addEnv["PATH"] = addEnv["PATH"].replace(";",":").replace("%PATH%", "$PATH")

        cmd = ""
        if DEBUG:
            cmd += "set -v off\n"
        for v in addEnv:
            cmd += "export " + v + "=" + addEnv[v]+"\n"
        
        if LOG:
            if cmds.find(">") < 0: # don't redirect if already use redirection
                list = cmds.split("\n")
                outf = " >> " + LOG_FILE+"\n"
                cmds = outf.join(list) + outf
        
        cmd += cmds
        return os.system(cmd)



def BUILD(pro_file, QMAKESPEC, QTDIR, RELEASE_SUFFIX, DESTDIR, APP_NAME):
    if os.name=="nt":
        return build_vs(pro_file, QMAKESPEC, QTDIR, DESTDIR, APP_NAME)
    else:
        return build_xcode_mac(pro_file, QMAKESPEC, QTDIR, RELEASE_SUFFIX, APP_NAME)

def build_xcode_mac(pro_file, QMAKESPEC, QTDIR, RELEASE_SUFFIX, APP_NAME):

    APP = APP_NAME+RELEASE_SUFFIX
    sdk = {
        "QTDIR" : QTDIR,
        "QMAKESPEC" : QMAKESPEC,
        "PATH" : "$PATH:" + QTDIR + "/bin",
    }
    # ------------------------------------	
    
    print ("Building...")
    if not os.path.exists("Release"+RELEASE_SUFFIX):
        os.makedirs("Release"+RELEASE_SUFFIX)
    
    shcall_mac(
        "xcodebuild -project " + APP + ".xcodeproj -configuration Release"
        , sdk
    )
    
    # output error
    if not os.path.exists("Release"+RELEASE_SUFFIX+"/" +APP_NAME+".app/Contents/MacOS/"+APP_NAME):
        error_report()
        return False
    else:
        print ("...build OK!")
        return True

        
        
def shcall(cmds, addEnv=[], log=False):
    ftmp = tempfile.NamedTemporaryFile(suffix='.cmd', prefix='tmp',delete=False)
    
    if not DEBUG and not log:
        ftmp.write("@echo off\n")
    for v in addEnv:
        ftmp.write(("set " + v + "=" + addEnv[v]+"\n").encode("utf-8"))
    ftmp.write(cmds.encode("utf-8"))
    fname = ftmp.name.replace("/","\\")
    ftmp.close()

    if log:
        log_message(getFile(fname))
    res = os.system("call "+fname + (" >> " + LOG_FILE if log else ""))

    if not DEBUG:
        os.remove(fname)

    return res


def shcall_mac(cmds, addEnv=[]):
    cmd = ""
    if DEBUG:
        cmd += "set -v off\n"
    for v in addEnv:
        cmd += "export " + v + "=" + addEnv[v]+"\n"
    
    if LOG:
        list = cmds.split("\n")
        outf = " >> " + LOG_FILE+"\n"
        cmds = outf.join(list) + outf
    
    cmd += cmds
    return os.system(cmd)

# for macos
# deprecated, use buildQmakeMake2 instead
def builQmakeMake(libname, buildRootDir, buildResult, sdk, CXXFLAGS):
    if os.path.exists(buildResult):
        print(buildResult + " is exist")
        return ""
    
    print("starting build " + libname + "...")
    
    cmd = []
    cmd.append(". "+sdk)
    cmd.append("cd " + buildRootDir)
    cmd.append("qmake")
    cmd.append('make CXXFLAGS="'+CXXFLAGS+'"')
    #cmd.append("make install")
    os.system("&&".join(cmd))	
    
    # check result
    if os.path.exists(buildResult):
        print("build Ok!")
        return buildResult
    else:
        print("build Fail!")
        return "-"


# for win+vs qmake and nmake
# deprecated, use buildQmakeMake2 instead
def builQmakeNmake(libname, buildRootDir, buildResult, sdk):
    
    if os.path.exists(buildResult):
        print(buildResult + " is exist")
        return ""
        
    print("")
    print("starting build " + libname + "...")
    
    cmd = []
    cmd.append("call "+sdk)
    cmd.append("cd " + buildRootDir.replace("/","\\"))
    cmd.append('qmake')
    cmd.append("nmake >>" + LOG_FILE)
    os.system("&".join(cmd))	
    
    # check result
    if os.path.exists(buildResult):
        print("build Ok!")
        return buildResult
    else:
        error_report()
        print("build Fail!")
        return "-"
    


    
# extracting tar archive to dir of archive-file
def untar(fname):
    print ("untar() is deplicated use extract() instead")
    
    fname = os.path.abspath(fname)
    fdir = os.path.dirname(fname);

    # clean previous extracted files
    for f in os.listdir(fdir):
        if os.path.basename(fname) != f:
            if os.path.isdir(fdir+"/"+f):
                shutil.rmtree(fdir+"/"+f, ignore_errors=True)
            else:
                os.remove(fdir+"/"+f)
    
    
    # calc tmp dir
    tmpdir = fdir.replace("\\","/") + "/tmp"
    
    # extracting to tmp
    print ("extracting " + fname + " ...")
    ar = tarfile.open(fname)
    ar.extractall(tmpdir)
    ar.close()
    
    rootdir = tmpdir
    # if archive has one dir then use its content
    if len(os.listdir(rootdir))==1:
        rootdir = rootdir + "/" + os.listdir(rootdir)[0];
    
        
    # move extracted files to root
    for f in os.listdir(rootdir):
        shutil.move(rootdir+"/"+f, fdir)
    
    # delete tmp dir
    shutil.rmtree(tmpdir, ignore_errors=True)
        
    return ""
    

def sign(key, password, exe, QMAKESPEC = ""):
    print ("sign() is deplicated, use sign2 instead")
    if len(QMAKESPEC)==0:
        QMAKESPEC = get_sdk()["QMAKESPEC"]
    shcall(
        '@call "%'+VSCOMNTOOLS[QMAKESPEC]+'%vsvars32.bat" > nul \n'
        + "signtool.exe sign"
        + " /f " + key.replace("/","\\")
        + " /p " + password
        + " " + exe.replace("/","\\"),
        log = LOG
    )
        

def curl(url, metod="GET", file="", headers={}):
    cmd = get_curl()
    cmd += " -X " + metod
    if len(file)>0:
        cmd += ' --data-binary "@' + file + '"'
        
    cmd += " " + url
    
    for h in headers:
        cmd += ' --header "' + h +": " + headers[h] + '"'

    res = CALL_WRAP(cmd)
    
    return res["message"]


def prepareMake(libname, buildRootDir, buildResult, QMAKESPEC, MAKEFLAGS="", CONFIGURE=""):
    print ("prepareMake() is deplicated use prepareMake2() instead")
    
    if os.path.exists(buildResult):
        print(buildResult + " is exist")
        return ""
        
    print("")
    print("starting build " + libname + "...")
    
    cmd = []
    cmd.append("cd " + buildRootDir)
    
    # do configure
    CONF_EXE = "configure"
    if os.name=="nt":
        CONF_EXE = CONF_EXE + ".exe"
    if os.path.exists(buildRootDir + "/" + CONF_EXE):
        cmd.append((".\\" if os.name=="nt" else "./") + CONF_EXE + " " + CONFIGURE)
    
    # do make
    if os.name=="nt":
        cmd.append("nmake")
    else:
        cmd.append('make ' + MAKEFLAGS)
    
    cmds = "\n".join(cmd)
    # enviroment
    if os.name=="nt":
        cmds = '@call "%' + VSCOMNTOOLS[QMAKESPEC] + '%vsvars32.bat" > nul\n' + cmds
    
    print(cmds)
    CALL_WRAP(cmds)
    
    # check result
    if os.path.exists(buildResult):
        print("build Ok!")
        return buildResult
    else:
        print("build Fail!")
        return "-"	
    
# deprecated, use smb_mount
# @folder = folder mount to
# @netpath network path, ex: //Server/Share
def mount(folder, netpath):
    if sys.platform == 'darwin':
        netpath = netpath.replace("//","//guest:@") # using guest for mac sharing
        fullpath = os.path.expanduser(folder)
        if not os.path.exists(fullpath):
            os.makedirs(fullpath)
        os.system('mount_smbfs -N '+netpath+' '+fullpath)
        return fullpath
    else:
        return netpath.replace(".local","")

# deprecated, use smb_umount    
def umount(folder):
    if sys.platform == 'darwin':
        os.system('umount '+folder)

    
main()
# version 1.6.6m
#	+ added check for homebrew
#	- improve default kit detection
# version 1.6.5m
# 	+ added support libssh libcurl +for macos
# version 1.6.3m
#	+ added get_sdk_var
# version 1.6.2m
# 	- fixed for macos build
# version 1.6.1m
#   + added curl2
# version 1.6m
#   + readcmd repleaced by extendend version of CALL() - CALL_WRAP()
#	+ added os_zip(), zip7() - now deprecated
#	- git_changes() adopted for win
# version 1.5m_win
# 	+ improve curl search (in git folder)
# 	* remove sdk.cmd creation
#   + findQt started first, and using for search default qt-kit (now only for win)
#   + added support msvc2015
#	+ in sdk.json added PATHS, QTKITS, MKSPECS (now only for win)
#	+ fincQt support qtcreator 4.0.3
# version 1.4.9m
# curl return get value
# version 1.4.8m
#	jso: warning_level=QUIET 
# version 1.4.7m
#	+ set_sdk_param, jsdoc
# version 1.4.6
#	+ log_message, git_changes, cmp_ver, parseInt
# version 1.4.5
#	+ added header for obfuscation
# version 1.4.4
#	* findQtWin replaced findQt and work for macos
# version 1.4.3
# 	+ added findQtWin() getCmdValue()
#	+ added curl 
#	+ added rcc compiler
#	+ added appstore function for deploy
#	+ support zip for download and extract
#	+ support configure
#	+ use MAKEFLAGS instead of CXXFLAGS only
#	+ win utils support unix paths
