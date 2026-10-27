#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <vector>
#define CK(x) do { auto e=(x); if(e!=cudaSuccess){fprintf(stderr,"%s: %s\n",#x,cudaGetErrorString(e));exit(2);} }while(0)
__global__ void copy_words(unsigned *dst, const unsigned *src, size_t n) {
 for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x) dst[i]=src[i];
}
int main(){
 int count; CK(cudaGetDeviceCount(&count)); if(count!=2)return 2;
 const size_t n=4*1024*1024, bytes=n*sizeof(unsigned);
 std::vector<unsigned> input(n), output(n); unsigned *buf[2];
 for(int g=0;g<2;g++){CK(cudaSetDevice(g));CK(cudaMalloc(&buf[g],bytes));CK(cudaDeviceEnablePeerAccess(1-g,0));}
 int failures=0;
 for(int src=0;src<2;src++)for(int mode=0;mode<3;mode++)for(int trial=0;trial<3;trial++){
  int dst=1-src; unsigned state=12345+trial;
  for(auto &v:input){state^=state<<13;state^=state>>17;state^=state<<5;v=state;}
  CK(cudaSetDevice(src)); CK(cudaMemcpy(buf[src],input.data(),bytes,cudaMemcpyHostToDevice));
  CK(cudaSetDevice(dst)); CK(cudaMemset(buf[dst],0,bytes)); CK(cudaDeviceSynchronize());
  CK(cudaSetDevice(mode==2?dst:src));
  if(mode==0)CK(cudaMemcpyPeer(buf[dst],dst,buf[src],src,bytes));
  else {copy_words<<<256,256>>>(buf[dst],buf[src],n);CK(cudaGetLastError());}
  CK(cudaDeviceSynchronize());CK(cudaSetDevice(dst));
  CK(cudaMemcpy(output.data(),buf[dst],bytes,cudaMemcpyDeviceToHost));
  size_t wrong=0;for(size_t i=0;i<n;i++)wrong+=output[i]!=input[i];
  printf("%d->%d %s trial=%d mismatched_words=%zu\n",src,dst,mode==0?"CE":mode==1?"SM-write":"SM-read",trial,wrong);
  if(wrong) printf("first expected=%08x actual=%08x next=%08x/%08x\n",input[0],output[0],input[1],output[1]);
  failures+=wrong!=0;
 }
 for(int g=0;g<2;g++){CK(cudaSetDevice(g));CK(cudaFree(buf[g]));}
 return failures?1:0;
}
