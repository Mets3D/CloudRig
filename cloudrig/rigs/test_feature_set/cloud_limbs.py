#====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

# <pep8 compliant>

import bpy

from rigify.utils.layers import DEF_LAYER
from rigify.utils.errors import MetarigError
from rigify.utils.rig import connected_children_names
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_bone_widget

from rigify.base_rig import BaseRig, stage


class Rig(BaseRig):
    """ A "copy_chain" rig.  All it does is duplicate the original bone chain
        and constrain it.
        This is a control and deformation rig.
    """
    def initialize(self):
        super().initialize()

        """ Gather and validate data about the rig.
        """
        self.type = self.params.type

    @stage.generate_bones
    def create_bones(self):
        for b in self.bones.org:
            # Let's just create some new bones for each existing bone with name dependent on the param.
            new_name = self.type
            self.copy_bone(b, new_name)

    ##############################
    # Parameters

    @classmethod
    def add_parameters(self, params):
        """ Add the parameters of this rig type to the
            RigifyParameters PropertyGroup
        """
        params.type = bpy.props.EnumProperty(name="Type",
        items= (
            ("ARM", "Arm", "Arm"),
            ("LEG", "Leg", "Leg"),
        ))

    @classmethod
    def parameters_ui(self, layout, params):
        """ Create the ui for the rig parameters.
        """
        r = layout.row()
        r.prop(params, "type")