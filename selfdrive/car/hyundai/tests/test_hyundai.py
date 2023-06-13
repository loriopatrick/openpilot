#!/usr/bin/env python3
import unittest
from collections import defaultdict

from cereal import car
from selfdrive.car.hyundai.values import CAMERA_SCC_CAR, CANFD_CAR, CAN_GEARS, CAR, CHECKSUM, FW_QUERY_CONFIG, \
                                         FW_VERSIONS, LEGACY_SAFETY_MODE_CAR, PART_NUMBER_FW_PATTERN, PLATFORM_CODE_FW_PATTERN

Ecu = car.CarParams.Ecu
ECU_NAME = {v: k for k, v in Ecu.schema.enumerants.items()}


class TestHyundaiFingerprint(unittest.TestCase):
  def test_canfd_not_in_can_features(self):
    can_specific_feature_list = set.union(*CAN_GEARS.values(), *CHECKSUM.values(), LEGACY_SAFETY_MODE_CAR, CAMERA_SCC_CAR)
    for car_model in CANFD_CAR:
      self.assertNotIn(car_model, can_specific_feature_list, "CAN FD car unexpectedly found in a CAN feature list")

  def test_auxiliary_request_ecu_whitelist(self):
    # Asserts only auxiliary Ecus can exist in database for CAN-FD cars
    whitelisted_ecus = {ecu for r in FW_QUERY_CONFIG.requests for ecu in r.whitelist_ecus if r.auxiliary}

    for car_model in CANFD_CAR:
      ecus = {fw[0] for fw in FW_VERSIONS[car_model].keys()}
      ecus_not_in_whitelist = ecus - whitelisted_ecus
      ecu_strings = ", ".join([f'Ecu.{ECU_NAME[ecu]}' for ecu in ecus_not_in_whitelist])
      self.assertEqual(len(ecus_not_in_whitelist), 0, f'{car_model}: Car model has ECUs not in auxiliary request whitelists: {ecu_strings}')

  def test_shared_part_numbers(self):
    all_part_numbers = defaultdict(set)
    for car_model, ecus in FW_VERSIONS.items():
      with self.subTest(car_model=car_model):
        if car_model == CAR.HYUNDAI_GENESIS:
          raise unittest.SkipTest("No part numbers for car model")

        for ecu, fws in ecus.items():
          if ecu[0] not in FW_QUERY_CONFIG.platform_code_ecus:
            continue

          for fw in fws:
            match = PART_NUMBER_FW_PATTERN.search(fw)
            code, date = PLATFORM_CODE_FW_PATTERN.search(fw).groups()
            print(code, date)
            all_part_numbers[(*ecu, code + b" " + match.group() + b" " + (date or b""))].add(car_model)
            self.assertIsNotNone(match, fw)

    for ecu, platforms in all_part_numbers.items():
      if len(platforms) > 1:
        print('shared parts', (ECU_NAME[ecu[0]], ecu[1], ecu[2], ecu[3]), platforms)

  def test_blacklisted_fws(self):
    blacklisted_fw = {(Ecu.fwdCamera, 0x7c4, None): [b'\xf1\x00NX4 FR_CMR AT USA LHD 1.00 1.00 99211-CW010 14X']}
    for car_model in FW_VERSIONS.keys():
      for ecu, fw in FW_VERSIONS[car_model].items():
        if ecu in blacklisted_fw:
          common_fw = set(fw).intersection(blacklisted_fw[ecu])
          self.assertTrue(len(common_fw) == 0, f'{car_model}: Blacklisted fw version found in database: {common_fw}')

  def test_platform_code_ecus_available(self):
    no_eps_platforms = CANFD_CAR | {CAR.KIA_SORENTO, CAR.KIA_OPTIMA_G4, CAR.KIA_OPTIMA_G4_FL,
                                    CAR.SONATA_LF, CAR.TUCSON, CAR.GENESIS_G90, CAR.GENESIS_G80}

    # Asserts ECU keys essential for fuzzy fingerprinting are available on all platforms
    for car_model, ecus in FW_VERSIONS.items():
      with self.subTest(car_model=car_model):
        for fuzzy_ecu in FW_QUERY_CONFIG.platform_code_ecus:
          if fuzzy_ecu in (Ecu.fwdRadar, Ecu.eps) and car_model == CAR.HYUNDAI_GENESIS:
            continue
          if fuzzy_ecu == Ecu.eps and car_model in no_eps_platforms:
            continue
          self.assertIn(fuzzy_ecu, [e[0] for e in ecus])

  def test_fw_part_number(self):
    # Hyundai places the ECU part number in their FW versions, assert all parsable
    # Some examples of valid formats: '56310-L0010', '56310L0010', '56310/M6300'
    for car_model, ecus in FW_VERSIONS.items():
      with self.subTest(car_model=car_model):
        if car_model == CAR.HYUNDAI_GENESIS:
          raise unittest.SkipTest("No part numbers for car model")

        for ecu, fws in ecus.items():
          if ecu[0] not in FW_QUERY_CONFIG.platform_code_ecus:
            continue

          for fw in fws:
            match = PART_NUMBER_FW_PATTERN.search(fw)
            self.assertIsNotNone(match, fw)

  def test_fuzzy_fw_dates(self):
    # Some newer platforms have date codes in a different format we don't yet parse,
    # for now assert date format is consistent for all FW across each platform
    for car_model, ecus in FW_VERSIONS.items():
      with self.subTest(car_model=car_model):
        for ecu, fws in ecus.items():
          if ecu[0] not in FW_QUERY_CONFIG.platform_code_ecus:
            continue

          codes = set()
          for fw in fws:
            codes |= FW_QUERY_CONFIG.fuzzy_get_platform_codes([fw])

          # Either no dates should be parsed or all dates should be parsed
          self.assertEqual(len({b'-' in code for code in codes}), 1)

  def test_fuzzy_platform_codes(self):
    # Asserts basic platform code parsing behavior
    codes = FW_QUERY_CONFIG.fuzzy_get_platform_codes([b'\xf1\x00DH LKAS 1.1 -150210'])
    self.assertEqual(codes, {b"DH-1502"})

    # Some cameras and all radars do not have dates
    codes = FW_QUERY_CONFIG.fuzzy_get_platform_codes([b'\xf1\x00AEhe SCC H-CUP      1.01 1.01 96400-G2000         '])
    self.assertEqual(codes, {b"AEhe"})

    codes = FW_QUERY_CONFIG.fuzzy_get_platform_codes([b'\xf1\x00CV1_ RDR -----      1.00 1.01 99110-CV000         '])
    self.assertEqual(codes, {b"CV1"})

    codes = FW_QUERY_CONFIG.fuzzy_get_platform_codes([
      b'\xf1\x00DH LKAS 1.1 -150210',
      b'\xf1\x00AEhe SCC H-CUP      1.01 1.01 96400-G2000         ',
      b'\xf1\x00CV1_ RDR -----      1.00 1.01 99110-CV000         ',
    ])
    self.assertEqual(codes, {b"DH-1502", b"AEhe", b"CV1"})

    # Returned platform codes must inclusively contain start/end dates
    codes = FW_QUERY_CONFIG.fuzzy_get_platform_codes([
      b'\xf1\x00LX2 MFC  AT USA LHD 1.00 1.07 99211-S8100 220222',
      b'\xf1\x00LX2 MFC  AT USA LHD 1.00 1.08 99211-S8100 211103',
      b'\xf1\x00ON  MFC  AT USA LHD 1.00 1.01 99211-S9100 190405',
      b'\xf1\x00ON  MFC  AT USA LHD 1.00 1.03 99211-S9100 190720',
    ])
    self.assertEqual(codes, {b'LX2-2111', b'LX2-2112', b'LX2-2201', b'LX2-2202',
                             b'ON-1904', b'ON-1905', b'ON-1906', b'ON-1907'})


if __name__ == "__main__":
  unittest.main()
