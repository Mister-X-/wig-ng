#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# wig-ng - Wireless Information Gathering New Generation
# Copyright (C) 2019 - Andrés Blanco (6e726d) <6e726d@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import struct

from Queue import Empty
from multiprocessing import Event

from helpers import ieee80211
from helpers.Processes import WigProcess

from impacket import ImpactDecoder
from impacket import dot11


class InformationElementsStats(WigProcess):
    """
    TODO: Documentation
    """

    SUBTYPE_WHITELIST = [
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_BEACON,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_PROBE_REQUEST,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_PROBE_RESPONSE,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_ASSOCIATION_REQUEST,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_ASSOCIATION_RESPONSE,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_REASSOCIATION_REQUEST,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_REASSOCIATION_RESPONSE,
    ]

    HDR_SIZE = {
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_BEACON: 12,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_PROBE_REQUEST: 0,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_PROBE_RESPONSE: 12,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_ASSOCIATION_REQUEST: 4,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_ASSOCIATION_RESPONSE: 6,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_REASSOCIATION_REQUEST: 10,
        dot11.Dot11Types.DOT11_SUBTYPE_MANAGEMENT_REASSOCIATION_RESPONSE: 6,
    }

    def __init__(self, frames_queue):
        WigProcess.__init__(self)
        self.__stop__ = Event()

        self.__queue__ = frames_queue

        self.decoder = ImpactDecoder.Dot11Decoder()
        self.decoder.FCS_at_end(False)

        self.__tag_stats__ = dict()

    def get_frame_type_filter(self):
        """
        Returns a list of IEEE 802.11 frame types supported by the module.
        """
        return [ieee80211.TYPE_MGMT]

    def get_frame_subtype_filter(self):
        """
        Returns a list of IEEE 802.11 frame subtypes supported by the module.
        """
        return [ieee80211.TYPE_MGMT_SUBTYPE_BEACON,
                ieee80211.TYPE_MGMT_SUBTYPE_PROBE_REQUEST,
                ieee80211.TYPE_MGMT_SUBTYPE_PROBE_RESPONSE,
                ieee80211.TYPE_MGMT_SUBTYPE_ASSOCIATION_REQUEST,
                ieee80211.TYPE_MGMT_SUBTYPE_ASSOCIATION_RESPONSE,
                ieee80211.TYPE_MGMT_SUBTYPE_REASSOCIATION_REQUEST,
                ieee80211.TYPE_MGMT_SUBTYPE_REASSOCIATION_RESPONSE]

    def run(self):
        """
        TODO: Documentation
        """
        self.set_process_title()

        try:
            self.malformed = 0
            while not self.__stop__.is_set():
                try:
                    frame = self.__queue__.get(timeout=5)
                    try:
                        self.decoder.decode(frame)
                    except Exception:
                        # print("Exception: %s" % e)
                        self.malformed +=1
                        continue
                    frame_control = self.decoder.get_protocol(dot11.Dot11)
                    if frame_control.get_subtype() in self.SUBTYPE_WHITELIST:
                        mgt_frame = self.decoder.get_protocol(dot11.Dot11ManagementFrame)
                        # Management frames shouldn't be fragmented.
                        # At least the ones we are processing.
                        seq_ctl = mgt_frame.get_sequence_control()
                        fragment_number = seq_ctl & 0x000F
                        if fragment_number == 0:
                            child = mgt_frame.child()
                            header_size = self.HDR_SIZE[frame_control.get_subtype()]
                            self.process_body(child, header_size)
                except Empty:
                    pass
        # Ignore SIGINT signal, this is handled by parent.
        except KeyboardInterrupt:
            pass

        for tag_id, count in self.__tag_stats__.items():
            print("TAG: %02X - %d" % (tag_id, count))
        print("Malformed frames: %d" % self.malformed)


    def process_body(self, child, offset):
        """
        TODO: Documentation
        """
        buff = child.get_header_as_string()[offset:]
        ies = InformationElementsStats.get_ie_list(buff)
        for ie in ies:
            (tag, length, value) = ie
            if tag not in self.__tag_stats__.keys():
                self.__tag_stats__[tag] = 1
            else:
                self.__tag_stats__[tag] += 1

    @staticmethod
    def get_ie_list(buff):
        """
        TODO: Documentation
        """
        result = list()
        idx = 0
        while True:
            if len(buff) < 3:
                break
            tag = struct.unpack("B", buff[idx])[0]
            length = struct.unpack("B", buff[idx+1])[0]
            value = buff[idx+2:idx+2+length]
            result.append((tag, length, value))
            idx += length + 2
            if idx >= len(buff):
                break
        return result

    def shutdown(self):
        """
        This method sets the __stop__ event to stop the process.
        """
        self.__stop__.set()