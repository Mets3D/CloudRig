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
from rigify.utils.bones import BoneDict, BoneUtilityMixin

from rigify.base_rig import BaseRig, stage

# Registerable rig template classes MUST be called exactly "Rig"!!!
# (This class probably shouldn't be registered in the future)
class Rig(BaseRig):
    """ Base for CloudRig arms and legs.
    """
    # overrides BaseRig.find_org_bones.
    def find_org_bones(self, bone):
        """Populate self.bones.org."""
        # For now we just grab all connected children of our main bone and pout it in self.bones.org.main.
        print("find org bones")
        return BoneDict(
            main=[bone.name] + connected_children_names(self.obj, bone.name),
        )

    def initialize(self):
        super().initialize()
        """Gather and validate data about the rig."""
        self.type = self.params.type
        print("initialize")

    # DSP bones - Display bones at the mid-point of each bone to use as display transforms.
    @stage.generate_bones
    def create_dsp_bones(self):
        print("create dsp bones")
        for b in self.bones.org.main:
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
        print("add params")
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