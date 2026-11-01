/* Hash and content sniffing worker for the durable upload queue.
 * Files are read in bounded chunks so selecting a 40k-file corpus does not
 * create a second in-memory copy of the corpus. */
const CHUNK_SIZE = 1024 * 1024;

function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
const K = [
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
];
class Sha256 {
  constructor() { this.h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]; this.bytes = 0; this.buf = new Uint8Array(0); }
  update(input) {
    const data = new Uint8Array(this.buf.length + input.length); data.set(this.buf); data.set(input, this.buf.length); this.bytes += input.length;
    let end = data.length - (data.length % 64);
    for (let i = 0; i < end; i += 64) this.block(data.subarray(i, i + 64));
    this.buf = data.slice(end); return this;
  }
  block(blockBytes) {
    const w = new Uint32Array(64); for (let i=0;i<16;i++) w[i] = (blockBytes[i*4]<<24)|(blockBytes[i*4+1]<<16)|(blockBytes[i*4+2]<<8)|blockBytes[i*4+3];
    for (let i=16;i<64;i++) { const x=w[i-15], y=w[i-2]; const s0=rotr(x,7)^rotr(x,18)^(x>>>3); const s1=rotr(y,17)^rotr(y,19)^(y>>>10); w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0; }
    let [a,b,c,d,e,f,g,h] = this.h;
    for (let i=0;i<64;i++) { const S1=rotr(e,6)^rotr(e,11)^rotr(e,25); const ch=(e&f)^(~e&g); const t1=(h+S1+ch+K[i]+w[i])>>>0; const S0=rotr(a,2)^rotr(a,13)^rotr(a,22); const maj=(a&b)^(a&c)^(b&c); const t2=(S0+maj)>>>0; h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0; }
    this.h = [(this.h[0]+a)>>>0,(this.h[1]+b)>>>0,(this.h[2]+c)>>>0,(this.h[3]+d)>>>0,(this.h[4]+e)>>>0,(this.h[5]+f)>>>0,(this.h[6]+g)>>>0,(this.h[7]+h)>>>0];
  }
  digest() { const bit = this.bytes * 8; const tail = new Uint8Array(((this.buf.length + 9 + 63) >> 6) * 64); tail.set(this.buf); tail[this.buf.length]=0x80; const view=new DataView(tail.buffer); view.setUint32(tail.length-4, bit>>>0); view.setUint32(tail.length-8, Math.floor(bit/0x100000000)>>>0); for(let i=0;i<tail.length;i+=64)this.block(tail.subarray(i,i+64)); return this.h.map(x=>x.toString(16).padStart(8,'0')).join(''); }
}
function sniff(bytes, name, declared) {
  if (bytes[0]===0x25&&bytes[1]===0x50&&bytes[2]===0x44&&bytes[3]===0x46) return 'application/pdf';
  if (bytes[0]===0xff&&bytes[1]===0xd8) return 'image/jpeg';
  if (bytes[0]===0x89&&bytes[1]===0x50&&bytes[2]===0x4e&&bytes[3]===0x47) return 'image/png';
  if (bytes[0]===0x47&&bytes[1]===0x49&&bytes[2]===0x46) return 'image/gif';
  if (bytes[0]===0x50&&bytes[1]===0x4b&&bytes[2]===0x03&&bytes[3]===0x04) return declared || 'application/zip';
  return declared || (name.toLowerCase().endsWith('.md') ? 'text/markdown' : 'application/octet-stream');
}
async function inspect(data) {
  try { const file=data.file; const hash=new Sha256(); let first=new Uint8Array(0);
    for(let offset=0; offset<file.size; offset+=CHUNK_SIZE) { const chunk=new Uint8Array(await file.slice(offset,offset+CHUNK_SIZE).arrayBuffer()); if(!first.length) first=chunk.slice(0,512); hash.update(chunk); }
    self.postMessage({id:data.id, sha256:hash.digest(), mime:sniff(first,data.name||file.name,data.mime||file.type), size:file.size});
  } catch (error) { self.postMessage({id:data.id,error:String(error)}); }
}
// One worker instance serves the whole page lifetime. Serializing inspections
// keeps the worker a scheduler rather than accidentally creating a hidden pool.
let inspectionTail = Promise.resolve();
self.onmessage = ({ data }) => {
  inspectionTail = inspectionTail.then(() => inspect(data));
  return inspectionTail;
};
