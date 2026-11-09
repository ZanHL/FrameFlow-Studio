"""macOS Keychain via Security.framework. Secrets never appear in process arguments."""
import ctypes as C
import os

class SecretStoreError(RuntimeError):pass
class MemoryStore:
    def __init__(self,*args):self.values={}
    def get(self,account):return self.values.get(account)
    def set(self,account,value):self.values[account]=value
    def delete(self,account):self.values.pop(account,None)

class KeychainStore:
    def __init__(self,service):
        self.service=service
        self.cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.sec=C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf.CFStringCreateWithCString.argtypes=[C.c_void_p,C.c_char_p,C.c_uint32];self.cf.CFStringCreateWithCString.restype=C.c_void_p
        self.cf.CFDataCreate.argtypes=[C.c_void_p,C.c_void_p,C.c_long];self.cf.CFDataCreate.restype=C.c_void_p
        self.cf.CFDictionaryCreate.argtypes=[C.c_void_p,C.POINTER(C.c_void_p),C.POINTER(C.c_void_p),C.c_long,C.c_void_p,C.c_void_p];self.cf.CFDictionaryCreate.restype=C.c_void_p
        self.cf.CFRelease.argtypes=[C.c_void_p]
        self.cf.CFDataGetLength.argtypes=[C.c_void_p];self.cf.CFDataGetLength.restype=C.c_long
        self.cf.CFDataGetBytePtr.argtypes=[C.c_void_p];self.cf.CFDataGetBytePtr.restype=C.c_void_p
        for name,args in [('SecItemCopyMatching',[C.c_void_p,C.POINTER(C.c_void_p)]),('SecItemAdd',[C.c_void_p,C.c_void_p]),('SecItemUpdate',[C.c_void_p,C.c_void_p]),('SecItemDelete',[C.c_void_p])]:
            f=getattr(self.sec,name);f.argtypes=args;f.restype=C.c_int32
    def const(self,name):return C.c_void_p.in_dll(self.sec if name.startswith('kSec') else self.cf,name).value
    def dictionary(self,values):
        refs=[];keys=[];vals=[]
        for k,v in values.items():
            keys.append(self.const(k))
            if isinstance(v,tuple):value=self.const(v[0])
            elif isinstance(v,bytes):value=self.cf.CFDataCreate(None,v,len(v));refs.append(value)
            else:value=self.cf.CFStringCreateWithCString(None,v.encode(),0x08000100);refs.append(value)
            vals.append(value)
        # Values remain alive for the duration of this synchronous Security call.
        d=self.cf.CFDictionaryCreate(None,(C.c_void_p*len(keys))(*keys),(C.c_void_p*len(vals))(*vals),len(keys),None,None)
        return d,refs
    def query(self,account):return {'kSecClass':('kSecClassGenericPassword',),'kSecAttrService':self.service,'kSecAttrAccount':account}
    def cleanup(self,d,refs):
        self.cf.CFRelease(d)
        for r in refs:self.cf.CFRelease(r)
    def check(self,status):
        if status:raise SecretStoreError('macOS 钥匙串操作失败（'+str(status)+'）。请解锁登录钥匙串并允许片场使用；未回退为明文保存。')
    def get(self,account):
        q=self.query(account);q['kSecReturnData']=('kCFBooleanTrue',);q['kSecMatchLimit']=('kSecMatchLimitOne',)
        d,refs=self.dictionary(q);result=C.c_void_p()
        try:
            status=self.sec.SecItemCopyMatching(d,C.byref(result))
            if status==-25300:return None
            self.check(status)
            return C.string_at(self.cf.CFDataGetBytePtr(result),self.cf.CFDataGetLength(result)).decode()
        finally:
            if result.value:self.cf.CFRelease(result)
            self.cleanup(d,refs)
    def set(self,account,value):
        d,refs=self.dictionary(self.query(account));attrs,arefs=self.dictionary({'kSecValueData':value.encode()})
        try:status=self.sec.SecItemUpdate(d,attrs)
        finally:self.cleanup(d,refs);self.cleanup(attrs,arefs)
        if status==-25300:
            q=self.query(account);q['kSecValueData']=value.encode();d,refs=self.dictionary(q)
            try:status=self.sec.SecItemAdd(d,None)
            finally:self.cleanup(d,refs)
        self.check(status)
    def delete(self,account):
        d,refs=self.dictionary(self.query(account))
        try:status=self.sec.SecItemDelete(d)
        finally:self.cleanup(d,refs)
        if status!=-25300:self.check(status)

class FileStore:
    """Private local credential file for systems without macOS Keychain."""
    def __init__(self, path):
        from pathlib import Path
        from filelock import FileLock
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + '.lock')
    def read(self):
        import json
        return json.loads(self.path.read_text()) if self.path.exists() else {}
    def get(self, account):
        with self.lock:
            return self.read().get(account)
    def set(self, account, value):
        import json
        with self.lock:
            values = self.read()
            if value is None: values.pop(account, None)
            else: values[account] = value
            temp = self.path.with_suffix('.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f: json.dump(values, f)
            os.replace(temp, self.path)
    def delete(self, account): self.set(account, None)
