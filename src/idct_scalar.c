/**
 * idct_scalar.c
 * Phase 1 Baseline: Pure scalar C implementation of 8x8 2D IDCT
 * Commonly used in video codecs (MPEG, H.264, JPEG) for decoding
 */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define WIDTH      3840
#define HEIGHT     2160
#define BLOCK_SIZE 8
#define PIXELS     (WIDTH * HEIGHT)
#define NUM_BLOCKS (PIXELS / (BLOCK_SIZE * BLOCK_SIZE))
#define ITERATIONS 10  // Compute-intensive, 10 iterations in 4K is extremely heavy

// Standard integer-scaled 8x8 DCT transform matrix (multiplied by 64)
static const int16_t C[8][8] = {
    {64,  64,  64,  64,  64,  64,  64,  64},
    {89,  75,  50,  18, -18, -50, -75, -89},
    {83,  36, -36, -83, -83, -36,  36,  83},
    {75, -18, -89, -50,  50,  89,  18, -75},
    {64, -64, -64,  64,  64, -64, -64,  64},
    {50, -89,  18,  75, -75, -18,  89, -50},
    {36, -83,  83, -36, -36,  83, -83,  36},
    {18, -50,  75, -89,  89, -75,  50, -18}
};

static inline uint8_t clamp_u8(int v) {
    if (v < 0)   return 0;
    if (v > 255) return 255;
    return (uint8_t)v;
}

// 2D IDCT row-column decomposition
void idct_8x8_block_scalar(const int16_t* in, uint8_t* out, int stride) {
    int16_t tmp[8][8];

    // 1. Transform rows
    for (int i = 0; i < 8; i++) {
        for (int j = 0; j < 8; j++) {
            int sum = 0;
            for (int k = 0; k < 8; k++) {
                sum += in[i * 8 + k] * C[j][k];
            }
            tmp[i][j] = (int16_t)(sum >> 6); // scale row
        }
    }

    // 2. Transform columns and clamp
    for (int j = 0; j < 8; j++) {
        for (int i = 0; i < 8; i++) {
            int sum = 0;
            for (int k = 0; k < 8; k++) {
                sum += C[i][k] * tmp[k][j];
            }
            out[i * stride + j] = clamp_u8(sum >> 12);
        }
    }
}

void idct_frame_scalar(const int16_t* coeff, uint8_t* img) {
    for (int by = 0; by < HEIGHT / 8; by++) {
        for (int bx = 0; bx < WIDTH / 8; bx++) {
            int block_idx = by * (WIDTH / 8) + bx;
            const int16_t* block_in = coeff + block_idx * 64;
            uint8_t* block_out = img + by * 8 * WIDTH + bx * 8;
            idct_8x8_block_scalar(block_in, block_out, WIDTH);
        }
    }
}

int main(void) {
    int16_t* coeff = (int16_t*)malloc(PIXELS * sizeof(int16_t));
    uint8_t* img = (uint8_t*)malloc(PIXELS);
    if (!coeff || !img) { fprintf(stderr, "malloc failed\n"); return 1; }

    // Init coefficients with simulated DCT frequency domain pattern
    for (int i = 0; i < PIXELS; i++) {
        coeff[i] = (int16_t)(((i % 64) == 0) ? (128 + (i % 256)) : ((i % 7) - 3));
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++) {
        idct_frame_scalar(coeff, img);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

    printf("[IDCT-SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n", elapsed, mpps);
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(coeff);
    free(img);
    return 0;
}
