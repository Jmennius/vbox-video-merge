"""Merge a video into vbox telemetry file"""
import argparse
import logging
import math
import re
from datetime import datetime, time, date, timedelta, timezone
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)
logging.basicConfig(format="{levelname:8} {message}", style='{', level=logging.INFO)


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
    logger.info(f"Patching headers...")
    if not 'avifileindex' in vbox_sections[VBOX_HEADER_SECTION]:
        vbox_sections[VBOX_HEADER_SECTION].append('avifileindex')
    if not 'avisynctime' in vbox_sections[VBOX_HEADER_SECTION]:
        vbox_sections[VBOX_HEADER_SECTION].append('avisynctime')
    logger.debug(f"New headers: {vbox_sections[VBOX_HEADER_SECTION]}")


def get_telemetry_column_names(vbox_sections) -> list[str]:
    return vbox_sections[VBOX_COLUMN_NAMES_SECTION][0].split()


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


def line_time_to_sec_and_time(line_time) -> tuple[float, time]:
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

    seconds_since_midnight = line_hour * 60 * 60 +  line_minutes * 60 + line_seconds + line_time_msec / 100

    return seconds_since_midnight, time(line_hour, line_minutes, line_seconds, line_time_msec * 1000)


def get_telemetry_start_time(vbox_sections, column_names: list[str]) -> time:
    time_col_idx = column_names.index('time')
    _, start_time = line_time_to_sec_and_time(float(vbox_sections[VBOX_DATA_SECTION][0].split()[time_col_idx]))
    return start_time


def patch_data(vbox_sections, column_names: list[str], video_number: str, video_offset_sec: float):
    logger.info(f"Patching data...")
    new_data_lines = list()

    time_col_idx = column_names.index('time')
    avifileindex_col_idx = column_names.index('avifileindex')
    avisynctime_col_idx = column_names.index('avisynctime')
    
    initial_time_sec, _ = line_time_to_sec_and_time(float(vbox_sections[VBOX_DATA_SECTION][0].split()[time_col_idx]))

    for data_line in vbox_sections[VBOX_DATA_SECTION]:
        data_line_elements = data_line.split()
        line_time_sec, _ = line_time_to_sec_and_time(float(data_line_elements[time_col_idx]))
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


def time_to_timedelta(time_obj: time) -> timedelta:
    return timedelta(hours=time_obj.hour, minutes=time_obj.minute,
                     seconds=time_obj.second, microseconds=time_obj.microsecond)

def get_probable_offset_from_sony_metadata(telemetry_start_time, metadata_filename):
    SONY_META_XMLNS = 'urn:schemas-professionalDisc:nonRealTimeMeta:ver.2.00'
    tree = ET.parse(metadata_filename)

    creation_date_element = tree.find(f'{{{SONY_META_XMLNS}}}CreationDate')
    creation_date = datetime.fromisoformat(creation_date_element.attrib['value'])
    logger.debug(f"CreationDate from metadata: {creation_date}")

    # GPS records start a bit later then the video itself
    gps_timestamp_element = tree.find(f"./{{{SONY_META_XMLNS}}}AcquisitionRecord/"
                                      f"{{{SONY_META_XMLNS}}}Group[@name='ExifGPS']/"
                                      f"{{{SONY_META_XMLNS}}}Item[@name='TimeStamp']")
    gps_timestamp = time.fromisoformat(gps_timestamp_element.attrib['value'])
    gps_datestamp_element = tree.find(f"./{{{SONY_META_XMLNS}}}AcquisitionRecord/"
                                      f"{{{SONY_META_XMLNS}}}Group[@name='ExifGPS']/"
                                      f"{{{SONY_META_XMLNS}}}Item[@name='DateStamp']")
    gps_datestamp = date.fromisoformat(gps_datestamp_element.attrib['value'].replace(':', '-'))
    logger.debug(f"GPS date: {gps_datestamp}, time: {gps_timestamp}")

    delta = time_to_timedelta(telemetry_start_time) - time_to_timedelta(creation_date.astimezone(timezone.utc).time())
    delta_sec = delta.seconds + (delta.microseconds / (1000 * 1000) )
    logger.info(f"Probable offset derived from video metadata: {delta_sec}s")
    return delta_sec


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Merge a video into vbox telemetry file")
    parser.add_argument('--vbox', required=True, help="vbox telemetry file")
    parser.add_argument('--merged-vbox', help="output vbox telemetry file with video merged (defaults to '_video' suffix)")
    parser.add_argument('--video', required=True, help="video file, should be in the same directory")
    parser.add_argument('--video-offset-sec', type=float, default=0,
                        help="Offset in the video where telemetry log starts in seconds."
                             "If guessing is enabled - this is added to the guessed time (can be negative).")
    parser.add_argument('--guess-offset-from', choices=['sony-metadata'], help="Try to guess video offset from metadata")

    args = parser.parse_args()

    merged_vbox_filename = args.merged_vbox if args.merged_vbox else args.vbox.split('.')[0] + '_video' + '.vbo'
    logger.info(f"Merging video {args.video} into vbox {args.vbox} as {merged_vbox_filename}")

    with open(args.vbox) as vbox_file:
        vbox_lines = vbox_file.readlines()
        logger.debug(f"VBox lines read: {len(vbox_lines)}")

        vbox_section_contents = read_vbox_sections(vbox_lines)
        # TODO: print venue and date from comment instead
        logger.info(f"VBox preamble: {vbox_section_contents[VBOX_PREAMBLE_SECTION][0]}")

        video_filename_match = re.fullmatch(r'(?P<prefix>[a-zA-Z]+)(?P<number>\d+).(?P<extension>\w+)', args.video)
        video_prefix = video_filename_match.group('prefix')
        video_number = video_filename_match.group('number')
        video_extension = video_filename_match.group('extension')
        logger.debug(f"Video file prefix: {video_prefix}, number: {video_number}, extension: {video_extension}")

        telemetry_start_time = get_telemetry_start_time(vbox_section_contents,
                                                        get_telemetry_column_names(vbox_section_contents))
        logger.debug(f"Telemetry start time: {telemetry_start_time}")

        video_offset_sec = args.video_offset_sec
        if args.guess_offset_from == 'sony-metadata':
            video_offset_sec += get_probable_offset_from_sony_metadata(telemetry_start_time,
                                                                       f"{video_prefix}{video_number}M01.XML")

        logger.info(f"Video offset to be used: {video_offset_sec}s")

        patch_headers(vbox_section_contents)
        telemetry_column_names = patch_column_names(vbox_section_contents)
        insert_avi_section(vbox_section_contents, video_prefix, video_extension)
        patch_data(vbox_section_contents, telemetry_column_names, video_number, video_offset_sec)

        write_vbox_sections(vbox_section_contents, merged_vbox_filename)
