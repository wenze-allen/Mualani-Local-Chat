#include "mtmd-helper.h"
#include "mtmd.h"

#include <map>

extern "C" {

mtmd_context_params mtmd_context_params_default(void) {
    return {};
}

mtmd_context * mtmd_init_from_file(
        const char *,
        const llama_model *,
        mtmd_context_params) {
    return nullptr;
}

void mtmd_free(mtmd_context *) {
}

bool mtmd_support_vision(const mtmd_context *) {
    return false;
}

bool mtmd_support_audio(const mtmd_context *) {
    return false;
}

void mtmd_bitmap_free(mtmd_bitmap *) {
}

mtmd_input_chunks * mtmd_input_chunks_init(void) {
    return nullptr;
}

size_t mtmd_input_chunks_size(const mtmd_input_chunks *) {
    return 0;
}

const mtmd_input_chunk * mtmd_input_chunks_get(
        const mtmd_input_chunks *,
        size_t) {
    return nullptr;
}

void mtmd_input_chunks_free(mtmd_input_chunks *) {
}

mtmd_input_chunk_type mtmd_input_chunk_get_type(const mtmd_input_chunk *) {
    return MTMD_INPUT_CHUNK_TYPE_TEXT;
}

const llama_token * mtmd_input_chunk_get_tokens_text(
        const mtmd_input_chunk *,
        size_t * n_tokens_output) {
    if (n_tokens_output != nullptr) {
        *n_tokens_output = 0;
    }
    return nullptr;
}

size_t mtmd_input_chunk_get_n_tokens(const mtmd_input_chunk *) {
    return 0;
}

const char * mtmd_input_chunk_get_id(const mtmd_input_chunk *) {
    return nullptr;
}

llama_pos mtmd_input_chunk_get_n_pos(const mtmd_input_chunk *) {
    return 0;
}

mtmd_input_chunk * mtmd_input_chunk_copy(const mtmd_input_chunk *) {
    return nullptr;
}

void mtmd_input_chunk_free(mtmd_input_chunk *) {
}

int32_t mtmd_tokenize(
        mtmd_context *,
        mtmd_input_chunks *,
        const mtmd_input_text *,
        const mtmd_bitmap **,
        size_t) {
    return 2;
}

mtmd_batch * mtmd_batch_init(mtmd_context *) {
    return nullptr;
}

void mtmd_batch_free(mtmd_batch *) {
}

int32_t mtmd_batch_add_chunk(mtmd_batch *, const mtmd_input_chunk *) {
    return 1;
}

int32_t mtmd_batch_encode(mtmd_batch *) {
    return 1;
}

float * mtmd_batch_get_output_embd(mtmd_batch *, const mtmd_input_chunk *) {
    return nullptr;
}

mtmd_caps mtmd_get_cap_from_file(const char *) {
    return {false, false};
}

void mtmd_helper_log_set(ggml_log_callback, void *) {
}

bool mtmd_helper_support_video(mtmd_context *) {
    return false;
}

mtmd_helper_bitmap_wrapper mtmd_helper_bitmap_init_from_buf(
        mtmd_context *,
        const unsigned char *,
        size_t,
        bool) {
    return {nullptr, nullptr};
}

int32_t mtmd_helper_decode_image_chunk(
        mtmd_context *,
        llama_context *,
        const mtmd_input_chunk *,
        float *,
        llama_pos,
        llama_seq_id,
        int32_t,
        llama_pos *,
        mtmd_helper_post_decode_callback,
        void *) {
    return -1;
}

void mtmd_helper_video_free(mtmd_helper_video *) {
}

} // extern "C"

std::map<ggml_backend_dev_t, size_t> mtmd_get_memory_usage(
        const char *,
        mtmd_context_params) {
    return {};
}
