#include "mualani-splash.h"

#include <array>
#include <string>
#include <string_view>

namespace {

static constexpr std::array<std::string_view, 9> main_mark = {
    "             CCC             ",
    "          CCCBBBCCC          ",
    "       CCBBBBBBBBBBBCC       ",
    "     CBBBBBWWBBBWWBBBBBC     ",
    "   CBBBBBBWWBBBBBWWBBBBBBC   ",
    "  CBBBBBBBBBBYYYBBBBBBBBBBC  ",
    " CBBBBBBCCCCCCCCCCCBBBBBBBBC ",
    "CBBBCCCCCBBBBBBBBBCCCCCBBBBC",
    "CCCCBBBBBBBBBBBBBBBBBBBCCCCC",
};

static constexpr std::array<std::string_view, 5> drop_mark = {
    "    C    ",
    "   CBC   ",
    "  CBBBC  ",
    " CBBBBBC ",
    "  CCCCC  ",
};

static constexpr std::array<std::string_view, 5> puffer_mark = {
    "   CCCCC   ",
    " CBBBBBBBC ",
    "CBBWBBBWBBC",
    " CBBBYYBBC ",
    "   CCCCC   ",
};

static constexpr std::array<std::array<std::string_view, 5>, 7> wordmark = {{
    {"#   #", "## ##", "# # #", "#   #", "#   #"},
    {"#   #", "#   #", "#   #", "#   #", " ### "},
    {" ### ", "#   #", "#####", "#   #", "#   #"},
    {"#    ", "#    ", "#    ", "#    ", "#####"},
    {" ### ", "#   #", "#####", "#   #", "#   #"},
    {"#   #", "##  #", "# # #", "#  ##", "#   #"},
    {"#####", "  #  ", "  #  ", "  #  ", "#####"},
}};

static std::string color_for(char pixel) {
    switch (pixel) {
        case 'B': return "\033[38;2;45;126;214m";
        case 'C': return "\033[38;2;74;210;224m";
        case 'W': return "\033[38;2;224;246;255m";
        case 'Y': return "\033[38;2;255;218;96m";
        default:  return {};
    }
}

static std::string render_pixels(std::string_view row, int scale) {
    std::string out;
    char active = '\0';
    for (const char pixel : row) {
        if (pixel == ' ') {
            if (active != '\0') {
                out += "\033[0m";
                active = '\0';
            }
            out.append(scale, ' ');
            continue;
        }
        if (pixel != active) {
            out += color_for(pixel);
            active = pixel;
        }
        for (int i = 0; i < scale; ++i) {
            out += "█";
        }
    }
    if (active != '\0') {
        out += "\033[0m";
    }
    return out;
}

static std::string render_wordmark(int row) {
    std::string out = "\033[1;38;2;56;148;232m";
    for (size_t glyph = 0; glyph < wordmark.size(); ++glyph) {
        for (const char cell : wordmark[glyph][row]) {
            out += cell == '#' ? "█" : " ";
        }
        if (glyph + 1 < wordmark.size()) {
            out += ' ';
        }
    }
    out += "\033[0m";
    return out;
}

} // namespace

std::string mualani_splash(bool use_color) {
    if (!use_color) {
        return "\nMUALANI\nLocal character chat\n";
    }

    static constexpr int canvas_width = 80;
    static constexpr int main_width = 31 * 2;
    static constexpr int left_width = 9;
    static constexpr int title_width = 41;
    static constexpr int right_width = 11;
    static constexpr int title_gap = 3;
    static constexpr int title_row_width =
        left_width + title_gap + title_width + title_gap + right_width;

    std::string out = "\n";
    for (const auto row : main_mark) {
        out.append((canvas_width - main_width) / 2, ' ');
        out += render_pixels(row, 2);
        out += '\n';
    }
    out += '\n';

    for (int row = 0; row < 5; ++row) {
        out.append((canvas_width - title_row_width) / 2, ' ');
        out += render_pixels(drop_mark[row], 1);
        out.append(title_gap, ' ');
        out += render_wordmark(row);
        out.append(title_gap, ' ');
        out += render_pixels(puffer_mark[row], 1);
        out += '\n';
    }
    const std::string subtitle = "local character chat | text edition";
    out.append((canvas_width - subtitle.size()) / 2, ' ');
    out += "\033[38;2;128;160;192m" + subtitle + "\033[0m\n";
    return out;
}
