#!/usr/bin/env python3
"""Exercise production ADL-S firmware clock and donor backlight fallbacks."""
from pathlib import Path
import os,re,subprocess,tempfile

root=Path(__file__).resolve().parents[1]
source=(root/'WhateverXe/kern_xe.cpp').read_text()
probe=re.search(r'uint64_t XE::wrapADLSCDClockProbe\(.*?\n\}',source,re.S).group()
backlight=re.search(r'uint32_t XE::wrapADLSPanelBacklight\(.*?\n\}',source,re.S).group()
start=source.index('    if (XELP::panelPWMDonorFallback &&')
filter=source[start:source.index('\n\tauto &tx = tglClockOffTransaction;',start)]
code=r'''
#include "kern_xelp_panel_pwm.hpp"
#include <cassert>
#include <cstring>
#define FunctionCast(f,p) reinterpret_cast<decltype(&f)>(p)
constexpr uint32_t kIOReturnNotReady=0xe00002d8;
struct IORegistryEntry {
 static IORegistryEntry *getRegistryRoot(){static IORegistryEntry r;return &r;}
 void setProperty(const char*,bool){}
 void setProperty(const char*,const void*,unsigned){}
};
static uint32_t floorValue=0;
static bool PE_parse_boot_argn(const char *name,void *out,unsigned){
 *static_cast<uint32_t*>(out)=!strcmp(name,"-wex-blmin")?floorValue:17777;return true;
}
struct XE {
 static XE *callbackXE;
 bool adlsDisplaySelected=true,display13FramebufferRequested=false;
 struct {unsigned panel=1;}adlsWiring,adlnOutputWiring;
 XELP::PanelPWM adlsPanelPWM;
 uintptr_t orgADLSCDClockProbe=0,adlsDisableCDClock=0,adlsSetCDClock=0,orgADLSPanelBacklight=0,orgTGLRegisterRead=0;
 struct {void (*getPG)(void*,unsigned);void (*putPG)(void*,unsigned);}tglTCNativeFunctions;
 static bool capture,target;
 static bool adlsCapturePanelPWM(void*){return capture;}
 static bool adlsPanelPWMTarget(void*,void *&a,void *&p){a=p=nullptr;return target;}
 static uint32_t display13PanelBrightness(void*,uint32_t){return 123;}
 static uint64_t wrapADLSCDClockProbe(void*);
 static uint32_t wrapADLSPanelBacklight(void*,uint32_t);
 static uint32_t wrapTGLRegisterRead(void*,unsigned long);
 static void wrapTGLRegisterWrite(void*,unsigned long,uint32_t);
};
XE *XE::callbackXE;bool XE::capture=false,XE::target=false;
static uint32_t decimal=0x158,reference=2,hardware=120000,last=0;
static unsigned disables=0,sets=0,probes=0,donors=0;
static uint64_t frequency=0;
static uint32_t adlsBlHw=0,adlsBlDonor=0;
uint32_t XE::wrapTGLRegisterRead(void*,unsigned long reg){
 if(reg==0x46000)return decimal;if(reg==0x51004)return reference<<29;
 if(reg==0x45404)return 1;if(reg==0x42000)return 0x1000000;
 assert(reg==0xc8254);return hardware;
}
void XE::wrapTGLRegisterWrite(void *access,unsigned long reg,uint32_t value){
 FILTER
 last=value;
}
static uint64_t disable(void*){++disables;return 0;}
static void set(void*,uint64_t v){++sets;frequency=v;decimal=0x518;}
static uint64_t originalProbe(void*){++probes;return decimal;}
static uint32_t originalBacklight(void*,uint32_t){++donors;return 456;}
static void power(void*,unsigned){}
PROBE
BACKLIGHT
int main(int argc,char**){
 floorValue=argc>1?1000:0;
 XE s;XE::callbackXE=&s;
 s.orgADLSCDClockProbe=(uintptr_t)originalProbe;s.adlsDisableCDClock=(uintptr_t)disable;s.adlsSetCDClock=(uintptr_t)set;
 s.orgADLSPanelBacklight=(uintptr_t)originalBacklight;s.orgTGLRegisterRead=(uintptr_t)XE::wrapTGLRegisterRead;
 s.tglTCNativeFunctions={power,power};
 alignas(void*) uint8_t controller[0xe60]{};void *access=controller;
 memcpy(controller+0xc40,&access,sizeof(access));
 const uint64_t pll[]={19200000ULL*68,24000000ULL*54,38400000ULL*34};
 for(reference=0;reference<3;++reference){
  decimal=0x158;unsigned before=sets;assert(XE::wrapADLSCDClockProbe(controller)==0x518);
  assert(sets==before+1&&disables==sets&&frequency==pll[reference]);
 }
 for(uint32_t known:{0x264U,0x26eU,0x44eU,0x458U,0x50eU,0x518U}){
  decimal=known;unsigned before=sets;assert(XE::wrapADLSCDClockProbe(controller)==known&&sets==before);
 }
 reference=3;decimal=0x158;assert(XE::wrapADLSCDClockProbe(controller)==0x158&&sets==3&&probes==10);
 assert(XE::wrapADLSPanelBacklight(controller,32768)==456&&donors==1&&XELP::panelPWMDonorFallback);
 // Default donor period before the donor has supplied a period write.
 XE::wrapTGLRegisterWrite(access,0xc8258,8888);
 assert(last==floorValue+uint64_t(8888)*(hardware-floorValue)/17777);
 XE::wrapTGLRegisterWrite(access,0xc8254,65535);assert(last==hardware&&adlsBlDonor==65535);
 XE::wrapTGLRegisterWrite(access,0xc8258,32768);
 assert(last==floorValue+uint64_t(32768)*(hardware-floorValue)/65535);
 XE::wrapTGLRegisterWrite(access,0xc8258,0);assert(last==floorValue);
 XE::wrapTGLRegisterWrite(access,0xc8258,~0U);assert(last==hardware);
 XELP::panelPWMBypass=true;XE::wrapTGLRegisterWrite(access,0xc8258,7);assert(last==7);XELP::panelPWMBypass=false;
 s.adlsDisplaySelected=false;XE::wrapTGLRegisterWrite(access,0xc8254,7);assert(last==7);s.adlsDisplaySelected=true;
 hardware=adlsBlHw=~0U;XE::wrapTGLRegisterWrite(access,0xc8258,9);assert(last==9);
 hardware=adlsBlHw=0;XE::wrapTGLRegisterWrite(access,0xc8258,10);assert(last==10);
 XE::capture=XE::target=true;s.adlsPanelPWM={120000,0};
 assert(XE::wrapADLSPanelBacklight(controller,65536)==kIOReturnNotReady&&donors==1);
 assert(!XE::wrapADLSPanelBacklight(controller,32768)&&!XELP::panelPWMBypass&&donors==1);
 assert(last==uint64_t(120000)*32768/65535);
}
'''.replace('FILTER',filter).replace('PROBE',probe).replace('BACKLIGHT',backlight)
# initializer_list is needed for the supported-clock sweep.
code='#include <initializer_list>\n'+code
with tempfile.TemporaryDirectory(prefix='adls-laptop-') as directory:
 p=Path(directory);(p/'test.cpp').write_text(code)
 subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I'+str(root/'WhateverXe'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 for args in ([],['floor']):subprocess.run([str(p/'test'),*args],check=True,env=dict(os.environ,UBSAN_OPTIONS='halt_on_error=1'))
print('PASS ADL-S unsupported/supported CDCLK, donor fallback, PWM scaling, floor, bypass and invalid periods')
