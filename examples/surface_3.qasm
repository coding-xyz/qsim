OPENQASM 3.0;
include "stdgates.inc";

qubit[17] q;

// 中途测量结果
bit[8] m1;
// 最终 X 基测量结果
bit[9] m2;

// --- RX 1 3 5 8 10 12 15 17 19
reset q[0];  h q[0];
reset q[2];  h q[2];
reset q[3];  h q[3];
reset q[4];  h q[4];
reset q[6];  h q[6];
reset q[8];  h q[8];
reset q[11]; h q[11];
reset q[13]; h q[13];
reset q[15]; h q[15];

// --- R 2 9 11 13 14 16 18 25
reset q[1];
reset q[5];
reset q[7];
reset q[9];
reset q[10];
reset q[12];
reset q[14];
reset q[16];

barrier q;

// --- H 2 11 16 25
h q[1];
h q[7];
h q[12];
h q[16];

barrier q;

// --- CX 2 3 16 17 11 12 15 14 10 9 19 18
cx q[1],  q[2];
cx q[12], q[13];
cx q[7],  q[8];
cx q[11], q[10];
cx q[6],  q[5];
cx q[15], q[14];

barrier q;

// --- CX 2 1 16 15 11 10 8 14 3 9 12 18
cx q[1],  q[0];
cx q[12], q[11];
cx q[7],  q[6];
cx q[4],  q[10];
cx q[2],  q[5];
cx q[8],  q[14];

barrier q;

// --- CX 16 10 11 5 25 19 8 9 17 18 12 13
cx q[12], q[6];
cx q[7],  q[3];
cx q[16], q[15];
cx q[4],  q[5];
cx q[13], q[14];
cx q[8],  q[9];

barrier q;

// --- CX 16 8 11 3 25 17 1 9 10 18 5 13
cx q[12], q[4];
cx q[7],  q[2];
cx q[16], q[13];
cx q[0],  q[5];
cx q[6],  q[14];
cx q[3],  q[9];

barrier q;

// --- H 2 11 16 25
h q[1];
h q[7];
h q[12];
h q[16];

barrier q;

// --- MR 2 9 11 13 14 16 18 25
m1[0] = measure q[1];   reset q[1];
m1[1] = measure q[5];   reset q[5];
m1[2] = measure q[7];   reset q[7];
m1[3] = measure q[9];   reset q[9];
m1[4] = measure q[10];  reset q[10];
m1[5] = measure q[12];  reset q[12];
m1[6] = measure q[14];  reset q[14];
m1[7] = measure q[16];  reset q[16];

// Stim 中的 DETECTOR 在标准 OpenQASM 里没有直接等价语法，
// 如需保留，需要另行在软件后处理中定义 syndrome 组合关系。

// --- MX 1 3 5 8 10 12 15 17 19
h q[0];  m2[0] = measure q[0];
h q[2];  m2[1] = measure q[2];
h q[3];  m2[2] = measure q[3];
h q[4];  m2[3] = measure q[4];
h q[6];  m2[4] = measure q[6];
h q[8];  m2[5] = measure q[8];
h q[11]; m2[6] = measure q[11];
h q[13]; m2[7] = measure q[13];
h q[15]; m2[8] = measure q[15];

// OBSERVABLE_INCLUDE(0) 也不是标准 OpenQASM 指令，
// 需要在外部按逻辑可观测量规则自行组合。
// 对应 Stim 里是 rec[-3] rec[-6] rec[-9] 的奇偶。