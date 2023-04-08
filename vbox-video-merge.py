"""Merge a video into vbox telemetry file"""
import argparse
import logging
import math
import re

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


VBOX_PREAMBLE_SECTION = 'preamble'  # pseudo section that we use to save the preamble
VBOX_HEADER_SECTION = 'header'
VBOX_AVI_SECTION = 'avi'
VBOX_COMMENTS_SECTION = 'comments'
VBOX_LAPTIMING_SECTION = 'laptiming'
VBOX_COLUMN_NAMES_SECTION = 'column names'
VBOX_DATA_SECTION = 'data'

VBOX_SECTION_ORDER = [VBOX_PREAMBLE_SECTION, VBOX_HEADER_SECTION, VBOX_AVI_SECTION, VBOX_COMMENTS_SECTION,
                      VBOX_LAPTIMING_SECTION, VBOX_COLUMN_NAMES_SECTION, VBOX_DATA_SECTION]


def read_vbox_sections(vbox_lines: list[str]) -> dict[str, list[str]]:
    """Groups vbox lines into sections
    
    There is a special section 'preamble' which contains everything before the first section.
    """
    vbox_section_contents = {VBOX_PREAMBLE_SECTION: []}
    current_section = VBOX_PREAMBLE_SECTION
    for line in vbox_lines:
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            vbox_section_contents[current_section] = list()
        elif line:  # skip empty lines
            vbox_section_contents[current_section].append(line)
    return vbox_section_contents


def write_vbox_sections(vbox_sections: list[str], filename):
    logger.info(f"Writing merged vbox...")
    merged_vbox_lines = []
    for section_name in VBOX_SECTION_ORDER:
        if section_name != VBOX_PREAMBLE_SECTION:  # do not write preamble section
            merged_vbox_lines.append('\n')
            merged_vbox_lines.append(f'[{section_name}]\n')
        for section_line in vbox_sections[section_name]:
            merged_vbox_lines.append(section_line + '\n')
    with open(filename, mode='w') as vbox_file:
        vbox_file.writelines(merged_vbox_lines)


def patch_headers(vbox_sections):
    logger.info(f"Patching heads...")
    if not 'avifileindex' in vbox_sections[VBOX_HEADER_SECTION]:
        vbox_sections[VBOX_HEADER_SECTION].append('avifileindex')
    if not 'avisynctime' in vbox_sections[VBOX_HEADER_SECTION]:
        vbox_sections[VBOX_HEADER_SECTION].append('avisynctime')
    logger.debug(f"New headers: {vbox_sections[VBOX_HEADER_SECTION]}")


def patch_column_names(vbox_sections) -> list[str]:
    logger.info(f"Patching column names...")
    column_names_list = vbox_sections[VBOX_COLUMN_NAMES_SECTION][0].split()
    if not 'avifileindex' in column_names_list:
        column_names_list.append('avifileindex')
    if not 'avisynctime' in column_names_list:
        column_names_list.append('avisynctime')
    vbox_sections[VBOX_COLUMN_NAMES_SECTION][0] = ' '.join(column_names_list)
    logger.debug(f"New column names: {vbox_sections[VBOX_COLUMN_NAMES_SECTION][0]}")
    return column_names_list


def insert_avi_section(vbox_sections, video_prefix: str, video_extension: str):
    logger.info(f"Inserting avi section...")
    vbox_sections[VBOX_AVI_SECTION] = [video_prefix, video_extension]
    logger.debug(f"avi section: {vbox_sections[VBOX_AVI_SECTION]}")


def line_time_to_sec(line_time) -> float:
    """Get time in seconds from line time
    
    Recorded time in each row is not in seconds -
    it's encoded by shifting hours, minutes and seconds into places
    """

    line_time_decimal_part, line_time_integer_part = math.modf(line_time)

    line_time_msec = round(line_time_decimal_part * 100)  # rounded to hundredth

    line_time_integer_part = int(line_time_integer_part)

    line_hour = int(line_time_integer_part / 10000)

    line_minutes = int((line_time_integer_part - line_hour * 10000)  / 100)

    line_seconds = int(line_time_integer_part - line_hour * 10000 - line_minutes * 100)

    return line_hour * 60 * 60 +  line_minutes * 60 + line_seconds + line_time_msec / 100


def patch_data(vbox_sections, column_names: list[str], video_number: str, video_offset_sec: float):
    logger.info(f"Patching data...")
    new_data_lines = list()

    time_col_idx = column_names.index('time')
    avifileindex_col_idx = column_names.index('avifileindex')
    avisynctime_col_idx = column_names.index('avisynctime')
    
    initial_time_sec = line_time_to_sec(float(vbox_sections[VBOX_DATA_SECTION][0].split()[time_col_idx]))

    for data_line in vbox_sections[VBOX_DATA_SECTION]:
        data_line_elements = data_line.split()
        line_time_sec = line_time_to_sec(float(data_line_elements[time_col_idx]))
        line_offset_sec = line_time_sec - initial_time_sec  # offset from beginning of telemetry

        line_video_offset_msec = round((video_offset_sec + line_offset_sec) * 1000)

        if avifileindex_col_idx < len(data_line_elements):
            data_line_elements[avifileindex_col_idx] = video_number
        else:
            data_line_elements.append(video_number)

        if avisynctime_col_idx < len(data_line_elements):
            data_line_elements[avisynctime_col_idx] = line_video_offset_msec
        else:
            data_line_elements.append(str(line_video_offset_msec))
        
        new_data_lines.append(' '.join(data_line_elements))
    
    vbox_sections[VBOX_DATA_SECTION] = new_data_lines


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Merge a video into vbox telemetry file")
    parser.add_argument('--vbox', required=True, help="vbox telemetry file")
    parser.add_argument('--merged-vbox', help="ourput vbox telemetry file with video merged (defaults to '_video' suffix)")
    parser.add_argument('--video', required=True, help="video file, should be in the same directory")
    parser.add_argument('--video-offset-sec', required=True, type=float, help="Offset in the video where telemetry log starts in ms.")

    args = parser.parse_args()

    merged_vbox_filename = args.merged_vbox if args.merged_vbox else args.vbox.split('.')[0] + '_video' + '.vbo'
    logger.info(f"Merging video {args.video} into vbox {args.vbox} as {merged_vbox_filename}")

    with open(args.vbox) as vbox_file:
        vbox_lines = vbox_file.readlines()
        logger.debug(f"VBox lines read: {len(vbox_lines)}")

        vbox_section_contents = read_vbox_sections(vbox_lines)
        logger.info(f"VBox preamble: {vbox_section_contents[VBOX_PREAMBLE_SECTION][0]}")

        video_filename_match = re.fullmatch(r'(?P<prefix>[a-zA-Z]+)(?P<number>\d+).(?P<extension>\w+)', args.video)
        video_prefix = video_filename_match.group('prefix')
        video_number = video_filename_match.group('number')
        video_extension = video_filename_match.group('extension')
        logger.info(f"Video file prefix: {video_prefix}, number: {video_number}, extension: {video_extension}")

        patch_headers(vbox_section_contents)
        column_names = patch_column_names(vbox_section_contents)
        insert_avi_section(vbox_section_contents, video_prefix, video_extension)
        patch_data(vbox_section_contents, column_names, video_number, args.video_offset_sec)

        write_vbox_sections(vbox_section_contents, merged_vbox_filename)
