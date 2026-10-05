import dgram from 'node:dgram';
import { randomBytes } from 'node:crypto';

const socket = dgram.createSocket('udp4');
const transaction = randomBytes(12);
const request = Buffer.alloc(20);
request.writeUInt16BE(0x0001, 0); // RFC 5389 Binding request
request.writeUInt32BE(0x2112a442, 4);
transaction.copy(request, 8);
let timer;
function finish(code) {
  clearTimeout(timer);
  socket.close();
  process.exitCode = code;
}
socket.once('error', () => finish(1));
socket.on('message', message => {
  if (
    message.length >= 20 &&
    message.readUInt16BE(0) === 0x0101 &&
    message.subarray(8, 20).equals(transaction)
  )
    finish(0);
});
timer = setTimeout(() => finish(1), 1000);
socket.send(request, Number(process.argv[3]), process.argv[2]);
