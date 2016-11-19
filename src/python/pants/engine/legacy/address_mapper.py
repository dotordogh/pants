# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import logging
import os

from pants.base.build_file import BuildFile
from pants.base.specs import DescendantAddresses, SiblingAddresses
from pants.build_graph.address_mapper import AddressMapper
from pants.engine.addressable import Addresses
from pants.engine.build_files import BuildDirs, BuildFiles
from pants.engine.engine import ExecutionError
from pants.engine.fs import Dir
from pants.engine.selectors import SelectDependencies
from pants.util.dirutil import fast_relpath


logger = logging.getLogger(__name__)


class LegacyAddressMapper(AddressMapper):
  """Provides an implementation of AddressMapper using v2 engine.

  This allows tasks to use the context's address_mapper when the v2 engine is enabled.
  """

  def __init__(self, scheduler, engine, build_root):
    self._scheduler = scheduler
    self._engine = engine
    self._build_root = build_root

  def scan_build_files(self, base_path):
    subject = DescendantAddresses(base_path)
    selector = SelectDependencies(BuildFiles, BuildDirs, field_types=(Dir,))
    request = self._scheduler.selection_request([(selector, subject)])

    result = self._engine.execute(request)
    if result.error:
      raise result.error

    build_files_set = set()
    for state in result.root_products.values():
      for build_files in state.value:
        build_files_set.update(f.path for f in build_files.files)

    return build_files_set

  @staticmethod
  def is_declaring_file(address, file_path):
    # NB: this will cause any BUILD file, whether it contains the address declaration or not to be
    # considered the one that declared it. That's ok though, because the spec path should be enough
    # information for debugging most of the time.
    #
    # We could call into the engine to ask for the file that declared the address.
    return (os.path.dirname(file_path) == address.spec_path and
            BuildFile._is_buildfile_name(os.path.basename(file_path)))

  def addresses_in_spec_path(self, spec_path):
    return self.scan_specs([SiblingAddresses(spec_path)])

  def scan_specs(self, specs, fail_fast=True):
    try:
      addresses = set(address
                      for a in self._engine.product_request(Addresses, specs)
                      for address in a.dependencies)
    except ExecutionError as e:
      raise self.BuildFileScanError(str(e))
    return addresses

  def scan_addresses(self, root=None):
    if root:
      try:
        base_path = fast_relpath(root, self._build_root)
      except ValueError as e:
        raise self.InvalidRootError(e)
    else:
      base_path = ''

    return self.scan_specs([DescendantAddresses(base_path)])