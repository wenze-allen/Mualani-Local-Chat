#pragma once

#include "common.h"

#include "cli-client.h"
#include "cli-server.h"

#include <atomic>
#include <memory>
#include <optional>
#include <string>
#include <fstream>

struct cli_timings {
    double prompt_per_second    = 0.0;
    double predicted_per_second = 0.0;
    int32_t prompt_tokens       = 0;
    int32_t predicted_tokens    = 0;
};

struct cli_context_impl;

struct cli_context {
    common_params params;

    cli_client client;                // always initialized
    std::optional<cli_server> server; // only set when no --server-base is given

    // properties of the connected server
    // will be populated by fetch_server_props()
    std::string model_name;
    std::string model_ftype;
    std::string build_info;
    bool has_vision = false;
    bool has_audio  = false;
    bool has_video  = false;

    std::optional<std::ofstream> output_file;

    cli_context(const common_params & params);
    ~cli_context();

    // connect to --server-base or spawn a local llama-server child;
    // argc/argv are needed to forward the server-relevant args to the child
    bool init();

    // run the interactive chat loop, returns the process exit code
    int run();

    // stop the local server child (if any)
    void shutdown();

    // set by the SIGINT handler; cleared once the interrupt has been handled
    static std::atomic<bool> & interrupted();

private:
    struct generated_content {
        std::string reasoning;
        std::string content;
    };
    bool generate_completion(
        generated_content & content_out,
        cli_timings & timings,
        bool display = true);
    void display_generated_content(const generated_content & content);
    bool review_draft_consistency(
        const std::string & user_text,
        const std::string & draft,
        std::string & conflict_reason);
    std::string build_draft_card_context(const std::string & draft);
    void fetch_server_props();
    void add_system_prompt();
    void rebuild_system_prompt();
    bool activate_character_cards_from_text(
        const std::string & text,
        bool announce = true);
    void reset_active_character_cards();
    void show_active_character_cards();
    bool activate_relationship_cards_from_text(
        const std::string & text,
        bool announce = true);
    void reset_active_relationship_cards();
    void show_active_relationship_cards();
    bool activate_world_lore_cards_from_text(
        const std::string & text,
        bool announce = true);
    void reset_active_world_lore_cards();
    void show_active_world_lore_cards();
    void push_user_message(const std::string & text);
    bool save_session_history();
    bool resume_session_history(const std::string & selection);
    void reset_session_history();
    bool save_runtime_preferences();
    int64_t count_context_tokens();
    bool maybe_auto_compact_history();
    bool compact_history(bool automatic, int64_t known_tokens = -1);
    bool write_compaction_checkpoint(int64_t tokens_before);
    bool select_response_mode(const std::string & selection);
    bool select_model(const std::string & selection);
    bool switch_local_model(const std::string & model_key);

    // check if server have multiple models (router mode)
    // if yes, list them then ask; do nothing otherwise
    bool list_and_ask_models();

#if !defined(MUALANI_TEXT_ONLY)
    bool stage_media_file(const std::string & fname, const std::string & type);
#endif

    // no-op if output file is not set
    void write_output_file(const std::string & content);

    std::unique_ptr<cli_context_impl> impl;
};
