cmake_minimum_required(VERSION 3.18)

set(UI_BINARY_DIR  "" CACHE STRING "UI binary directory")
set(LLAMA_UI_EMBED "" CACHE STRING "Path to llama-ui-embed helper")

if(NOT MUALANI_TEXT_ONLY)
    message(FATAL_ERROR "This downstream asset script is only for MUALANI_TEXT_ONLY builds")
endif()

set(DIST_DIR "${UI_BINARY_DIR}/dist")
set(UI_CPP    "${UI_BINARY_DIR}/ui.cpp")
set(UI_H      "${UI_BINARY_DIR}/ui.h")

file(REMOVE_RECURSE "${DIST_DIR}")
execute_process(
    COMMAND "${LLAMA_UI_EMBED}" "${UI_CPP}" "${UI_H}"
    RESULT_VARIABLE rc
)
if(NOT rc EQUAL 0)
    message(FATAL_ERROR "UI: llama-ui-embed failed (${rc})")
endif()
