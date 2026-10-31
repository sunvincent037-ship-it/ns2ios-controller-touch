#include "../fc27_native_display_core.h"
#include <assert.h>
#include <stdio.h>

static const uint64_t B=0x100000000ull,O=0x200000000ull,S=0x300000000ull;
static uint64_t owner,settings,type,record;
static uint8_t object[0x130],renderer[0x2500];
static uint32_t resize[8]={0xf951d669,0x39442928,0x7100051f,0x540000a1,0xb940a528,0xb9001fa8,0xb9409529,0x14000028};
static uint32_t startup[8]={0xf951d6a9,0x39442928,0x7100051f,0x540000a1,0xb940a528,0xb9001fa8,0xb9409529,0x14000028};
static int writes;
static int r(void *ctx,uint64_t a,void *out,size_t n){
    (void)ctx;void *p=NULL;
    if(a==B+0xde7cd10&&n==8)p=&owner;
    if(a==O+0x23a8&&n==8)p=&settings;
    if(a==S+8&&n==8)p=&type;
    if(a==B+0xda01b88&&n==8)p=&record;
    if(a==B+0x9786568&&n==32)p=resize;
    if(a==B+0x978675c&&n==32)p=startup;
    if(a>=S&&a-S+n<=sizeof object&&a!=S+8)p=object+(a-S);
    if(!p)return 0;memcpy(out,p,n);return 1;
}
static void w(void *ctx,uint64_t a,const void *in,size_t n){
    (void)ctx;
    if(a>=S&&a-S+n<=sizeof object)memcpy(object+(a-S),in,n);
    else {assert(a==O+0x247c&&n==1);memcpy(renderer+0x247c,in,n);}
    writes++;
}
static int apply(const char *b,int width,int height){return fc27_native_display_apply(b,B,width,height,r,w,NULL);}
static const char *build="fb81983aa1cc3a2e97402497e2ca6528";
static uint32_t u32(size_t o){uint32_t v;memcpy(&v,object+o,4);return v;}
int main(void){
    owner=O;settings=S;type=B+0xda01b88;record=B+0xd1ff800;
    object[0x128]=1;
    assert(apply(build,2420,1668)==FC27_DISPLAY_CHANGED);assert(writes==5);
    assert(u32(0xa4)==2420&&u32(0x94)==1668&&object[0x10a]==1&&object[0x128]==0&&renderer[0x247c]==1);
    assert(apply(build,2420,1668)==FC27_DISPLAY_UNCHANGED&&writes==5);
    assert(apply("a48c0de3bc353efa0e4d359bde05ef24",2420,1668)==FC27_DISPLAY_REJECT&&writes==5);
    assert(apply(build,0,1668)==FC27_DISPLAY_REJECT&&writes==5);
    owner=0;assert(apply(build,2420,1668)==FC27_DISPLAY_PENDING&&writes==5);owner=O;
    settings=0;assert(apply(build,2420,1668)==FC27_DISPLAY_PENDING&&writes==5);settings=S;
    type++;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);type--;
    record++;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);record--;
    resize[0]++;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);resize[0]--;
    startup[0]++;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);startup[0]--;
    object[0x10a]=2;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);object[0x10a]=1;
    object[0x128]=2;assert(apply(build,2420,1668)==FC27_DISPLAY_REJECT&&writes==5);object[0x128]=0;
    assert(apply(build,1668,2420)==FC27_DISPLAY_CHANGED&&writes==8);
    assert(u32(0xa4)==1668&&u32(0x94)==2420);
    renderer[0x247c]=0;object[0x10a]=0;
    assert(apply(build,1668,2420)==FC27_DISPLAY_CHANGED&&writes==10&&renderer[0x247c]==1);
    puts("14 native-display core cases passed (synthetic memory; no live-screen claim)");
    return 0;
}
