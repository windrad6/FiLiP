"""
created Sep 21, 2021

@author Thomas Storek

NGSIv2 models for context broker interaction
"""
import json
from datetime import datetime
from typing import Any, Type, List, Dict, Union, Optional, Pattern, Set
from aenum import Enum
from filip.utils.simple_ql import QueryString, QueryStatement
from pydantic import \
    BaseModel, \
    create_model, \
    Field, \
    root_validator, \
    validator, AnyHttpUrl, Json

from filip.models.ngsi_v2.base import EntityPattern, Expression
from filip.models.base import DataType, FiwareRegex
from filip.models.ngsi_v2.units import validate_unit_data


class GetEntitiesOptions(str, Enum):
    """ Options for queries"""
    _init_ = 'value __doc__'

    NORMALIZED = "normalized", "Normalized message representation"
    KEY_VALUES = "keyValues", "Key value message representation." \
                              "This mode represents the entity " \
                              "attributes by their values only, leaving out " \
                              "the information about type and metadata. " \
                              "See example " \
                              "below." \
                              "Example: " \
                              "{" \
                              "  'id': 'R12345'," \
                              "  'type': 'Room'," \
                              "  'temperature': 22" \
                              "}"
    VALUES = "values", "Key value message representation. " \
                       "This mode represents the entity as an array of " \
                       "attribute values. Information about id and type is " \
                       "left out. See example below. The order of the " \
                       "attributes in the array is specified by the attrs " \
                       "URI param (e.g. attrs=branch,colour,engine). " \
                       "If attrs is not used, the order is arbitrary. " \
                       "Example:" \
                       "[ 'Ford', 'black', 78.3 ]"
    UNIQUE = 'unique', "unique mode. This mode is just like values mode, " \
                       "except that values are not repeated"


# NGSIv2 entity models
class ContextMetadata(BaseModel):
    """
    Context metadata is used in FIWARE NGSI in several places, one of them being
    an optional part of the attribute value as described above. Similar to
    attributes, each piece of metadata has.

    Note:
         In NGSI it is not foreseen that metadata may contain nested metadata.
    """
    type: Optional[Union[DataType, str]] = Field(
        title="metadata type",
        description="a metadata type, describing the NGSI value type of the "
                    "metadata value Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.standard.value  # Make it FIWARE-Safe
    )
    value: Optional[Any] = Field(
        title="metadata value",
        description="a metadata value containing the actual metadata"
    )

    @validator('value', allow_reuse=True)
    def validate_value(cls, value):
        assert json.dumps(value), "metadata not serializable"
        return value


class NamedContextMetadata(ContextMetadata):
    """
    Model for metadata including a name
    """
    name: str = Field(
        titel="metadata name",
        description="a metadata name, describing the role of the metadata in "
                    "the place where it occurs; for example, the metadata name "
                    "accuracy indicates that the metadata value describes how "
                    "accurate a given attribute value is. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.standard.value  # Make it FIWARE-Safe
    )

    @root_validator
    def validate_data(cls, values):
        if values.get("name", "").casefold() in ["unit",
                                                 "unittext",
                                                 "unitcode"]:
            values.update(validate_unit_data(values))
        return values

    def to_context_metadata(self):
        return {self.name: ContextMetadata(**self.dict())}


class ContextAttribute(BaseModel):
    """
    Model for an attribute is represented by a JSON object with the following
    syntax:

    The attribute value is specified by the value property, whose value may
    be any JSON datatype.

    The attribute NGSI type is specified by the type property, whose value
    is a string containing the NGSI type.

    The attribute metadata is specified by the metadata property. Its value
    is another JSON object which contains a property per metadata element
    defined (the name of the property is the name of the metadata element).
    Each metadata element, in turn, is represented by a JSON object
    containing the following properties:

    Values of entity attributes. For adding it you need to nest it into a
    dict in order to give it a name.

    Example:

        >>> data = {"value": <...>,
                    "type": <...>,
                    "metadata": <...>}
        >>> attr = ContextAttribute(**data)

    """
    type: Union[DataType, str] = Field(
        default=DataType.TEXT,
        description="The attribute type represents the NGSI value type of the "
                    "attribute value. Note that FIWARE NGSI has its own type "
                    "system for attribute values, so NGSI value types are not "
                    "the same as JSON types. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.standard.value,  # Make it FIWARE-Safe
    )
    value: Optional[Union[Union[float, int, bool, str, List, Dict[str, Any]],
                          List[Union[float, int, bool, str, List,
                                     Dict[str, Any]]]]] = Field(
        default=None,
        title="Attribute value",
        description="the actual data"
    )
    metadata: Optional[Union[Dict[str, ContextMetadata],
                             NamedContextMetadata,
                             List[NamedContextMetadata]]] = Field(
        default={},
        title="Metadata",
        description="optional metadata describing properties of the attribute "
                    "value like e.g. accuracy, provider, or a timestamp")

    @validator('value')
    def validate_value_type(cls, value, values):
        """validator for field 'value'"""
        type_ = values['type']
        if value:
            if type_ == DataType.TEXT:
                if isinstance(value, list):
                    return [str(item) for item in value]
                return str(value)
            if type_ == DataType.BOOLEAN:
                if isinstance(value, list):
                    return [bool(item) for item in value]
                return bool(value)
            if type_ in (DataType.NUMBER, DataType.FLOAT):
                if isinstance(value, list):
                    return [float(item) for item in value]
                return float(value)
            if type_ == DataType.INTEGER:
                if isinstance(value, list):
                    return [int(item) for item in value]
                return int(value)
            if type_ == DataType.DATETIME:
                return value
            if type_ == DataType.ARRAY:
                if isinstance(value, list):
                    return value
                raise TypeError(f"{type(value)} does not match "
                                f"{DataType.ARRAY}")
            if type_ == DataType.STRUCTUREDVALUE:
                value = json.dumps(value)
                return json.loads(value)
            else:
                value = json.dumps(value)
                return json.loads(value)
        return value

    @validator('metadata')
    def validate_metadata_type(cls, value):
        """validator for field 'metadata'"""
        if isinstance(value, NamedContextMetadata):
            value = [value]
        elif isinstance(value, dict):
            if all(isinstance(item, ContextMetadata)
                   for item in value.values()):
                return value
            json.dumps(value)
            return {key: ContextMetadata(**item) for key, item in value.items()}
        if isinstance(value, list):
            if all(isinstance(item, NamedContextMetadata) for item in value):
                return {item.name: ContextMetadata(**item.dict(exclude={
                    'name'})) for item in value}
            if all(isinstance(item, Dict) for item in value):
                return {key: ContextMetadata(**item) for key, item in value}
        raise TypeError(f"Invalid type {type(value)}")


class NamedContextAttribute(ContextAttribute):
    """
    Context attributes are properties of context entities. For example, the
    current speed of a car could be modeled as attribute current_speed of entity
    car-104.

    In the NGSI data model, attributes have an attribute name, an attribute type
    an attribute value and metadata.
    """
    name: str = Field(
        titel="Attribute name",
        description="The attribute name describes what kind of property the "
                    "attribute value represents of the entity, for example "
                    "current_speed. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.string_protect.value,
        # Make it FIWARE-Safe
    )


class ContextEntityKeyValues(BaseModel):
    """
    Base Model for an entity is represented by a JSON object with the following
    syntax.

    The entity id is specified by the object's id property, whose value
    is a string containing the entity id.

    The entity type is specified by the object's type property, whose value
    is a string containing the entity's type name.

    """
    id: str = Field(
        ...,
        title="Entity Id",
        description="Id of an entity in an NGSI context broker. Allowed "
                    "characters are the ones in the plain ASCII set, except "
                    "the following ones: control characters, "
                    "whitespace, &, ?, / and #.",
        example='Bcn-Welt',
        max_length=256,
        min_length=1,
        regex=FiwareRegex.standard.value,  # Make it FIWARE-Safe
        allow_mutation=False
    )
    type: str = Field(
        ...,
        title="Entity Type",
        description="Id of an entity in an NGSI context broker. "
                    "Allowed characters are the ones in the plain ASCII set, "
                    "except the following ones: control characters, "
                    "whitespace, &, ?, / and #.",
        example="Room",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.standard.value,  # Make it FIWARE-Safe
        allow_mutation=False
    )

    class Config:
        """
        Pydantic config
        """
        extra = 'allow'
        validate_all = True
        validate_assignment = True


class PropertyFormat(str, Enum):
    """
    Format to decide if properties of ContextEntity class are returned as
    List of NamedContextAttributes or as Dict of ContextAttributes.
    """
    LIST = 'list'
    DICT = 'dict'


class ContextEntity(ContextEntityKeyValues):
    """
    Context entities, or simply entities, are the center of gravity in the
    FIWARE NGSI information model. An entity represents a thing, i.e., any
    physical or logical object (e.g., a sensor, a person, a room, an issue in
    a ticketing system, etc.). Each entity has an entity id.
    Furthermore, the type system of FIWARE NGSI enables entities to have an
    entity type. Entity types are semantic types; they are intended to describe
    the type of thing represented by the entity. For example, a context
    entity #with id sensor-365 could have the type temperatureSensor.

    Each entity is uniquely identified by the combination of its id and type.

    The entity id is specified by the object's id property, whose value
    is a string containing the entity id.

    The entity type is specified by the object's type property, whose value
    is a string containing the entity's type name.

    Entity attributes are specified by additional properties, whose names are
    the name of the attribute and whose representation is described in the
    "ContextAttribute"-model. Obviously, id and type are
    not allowed to be used as attribute names.

    Example:

        >>> data = {'id': 'MyId',
                    'type': 'MyType',
                    'my_attr': {'value': 20, 'type': 'Number'}}

        >>> entity = ContextEntity(**data)

    """
    def __init__(self, id: str, type: str, **data):

        # There is currently no validation for extra fields
        data.update(self._validate_attributes(data))
        super().__init__(id=id, type=type, **data)

    class Config:
        """
        Pydantic config
        """
        extra = 'allow'
        validate_all = True
        validate_assignment = True

    @classmethod
    def _validate_attributes(cls, data: Dict):
        attrs = {key: ContextAttribute.parse_obj(attr) for key, attr in
                 data.items() if key not in ContextEntity.__fields__}
        return attrs

    def add_attributes(self, attrs: Union[Dict[str, ContextAttribute],
                                          List[NamedContextAttribute]]) -> None:
        """
        Add property to entity
        Args:
            attrs:
        Returns:
            None
        """
        if isinstance(attrs, list):
            attrs = {attr.name: ContextAttribute(**attr.dict(exclude={'name'}))
                     for attr in attrs}
        for key, attr in attrs.items():
            self.__setattr__(name=key, value=attr)

    def get_attributes(
            self,
            whitelisted_attribute_types: Optional[List[DataType]] = None,
            blacklisted_attribute_types: Optional[List[DataType]] = None,
            response_format: Union[str, PropertyFormat] = PropertyFormat.LIST) \
            -> Union[List[NamedContextAttribute], Dict[str, ContextAttribute]]:

        response_format = PropertyFormat(response_format)

        assert whitelisted_attribute_types is None or \
               blacklisted_attribute_types is None,\
               "Only whitelist or blacklist is allowed"

        if whitelisted_attribute_types is not None:
            attribute_types = whitelisted_attribute_types
        elif blacklisted_attribute_types is not None:
            attribute_types = [att_type for att_type in list(DataType)
                               if att_type not in blacklisted_attribute_types]
        else:
            attribute_types = [att_type for att_type in list(DataType)]

        if response_format == PropertyFormat.DICT:
            return {key: ContextAttribute(**value)
                    for key, value in self.dict().items()
                    if key not in ContextEntity.__fields__
                    and value.get('type') in
                    [att.value for att in attribute_types]}
        else:
            return [NamedContextAttribute(name=key, **value)
                    for key, value in self.dict().items()
                    if key not in ContextEntity.__fields__
                    and value.get('type') in
                    [att.value for att in attribute_types]]

    def get_attribute_names(self) -> Set[str]:
        """
        Returns a set with all attribute names of this entity

        Returns:
            set[str]
        """

        return {key for key in self.dict()
                if key not in ContextEntity.__fields__}

    def delete_attributes(self, attrs: Union[Dict[str, ContextAttribute],
                                             List[NamedContextAttribute],
                                             List[str]]):
        """
        Delete the given attributes from the entity

        Args:
            attrs:  - Dict {name: ContextAttribute}
                    - List[NamedContextAttribute]
                    - List[str] -> names of attributes
        Raises:
            Exception: if one of the given attrs does not represent an
                       existing argument
        """

        names: List[str] = []
        if isinstance(attrs, list):
            for entry in attrs:
                if isinstance(entry, str):
                    names.append(entry)
                elif isinstance(entry, NamedContextAttribute):
                    names.append(entry.name)
        else:
            names.extend(list(attrs.keys()))
        for name in names:
            delattr(self, name)

    def get_attribute(self, attribute_name) -> NamedContextAttribute:
        for attr in self.get_attributes():
            if attr.name == attribute_name:
                return attr

    def get_properties(
            self,
            response_format: Union[str, PropertyFormat] = PropertyFormat.LIST)\
            -> Union[List[NamedContextAttribute], Dict[str, ContextAttribute]]:
        """
        Args:
            response_format:

        Returns:

        """
        return self.get_attributes(blacklisted_attribute_types=[
            DataType.RELATIONSHIP], response_format=response_format)

    def get_relationships(
            self,
            response_format: Union[str, PropertyFormat] = PropertyFormat.LIST)\
            -> Union[List[NamedContextAttribute], Dict[str, ContextAttribute]]:
        """
        Get all relationships of the context entity

        Args:
            response_format:

        Returns:

        """
        return self.get_attributes(whitelisted_attribute_types=[
            DataType.RELATIONSHIP], response_format=response_format)


def create_context_entity_model(name: str = None,
                                data: Dict = None,
                                validators: Dict[str, Any] = None) -> \
        Type['ContextEntity']:
    r"""
    Creates a ContextEntity-Model from a dict:

    Args:
        name: name of the model
        data: dictionary containing the data structure
        validators (optional): validators for the new model

    Example:

        >>> def username_alphanumeric(cls, value):
                assert v.value.isalnum(), 'must be numeric'
                return value

        >>> model = create_context_entity_model(
                        name='MyModel',
                        data={
                            'id': 'MyId',
                            'type':'MyType',
                            'temp': 'MyProperty'}
                        {'validate_test': validator('temperature')(
                            username_alphanumeric)})

    Returns:
        ContextEntity

    """
    properties = {key: (ContextAttribute, ...) for key in data.keys() if
                  key not in ContextEntity.__fields__}
    model = create_model(
        __model_name=name or 'GeneratedContextEntity',
        __base__=ContextEntity,
        __validators__=validators or {},
        **properties
    )
    return model


class Query(BaseModel):
    """
    Model for queries
    """
    entities: List[EntityPattern] = Field(
        description="a _list of entities to search for. Each element is "
                    "represented by a JSON object"
    )
    attrs: Optional[List[str]] = Field(
        description="List of attributes to be provided "
                    "(if not specified, all attributes)."
    )
    expression: Optional[Expression] = Field(
        description="An expression composed of q, mq, georel, geometry and "
                    "coords "
    )
    metadata: Optional[List[str]] = Field(
        description='a _list of metadata names to include in the response. '
                    'See "Filtering out attributes and metadata" section for '
                    'more detail.'
    )


class ActionType(str, Enum):
    """
    Options for queries
    """
    _init_ = 'value __doc__'
    APPEND = "append", "maps to POST /v2/entities (if the entity does not " \
                       "already exist) or POST /v2/entities/<id>/attrs (if " \
                       "the entity already exists). "
    APPEND_STRICT = "appendStrict", "maps to POST /v2/entities (if the " \
                                    "entity does not already exist) or POST " \
                                    "/v2/entities/<id>/attrs?options=append " \
                                    "(if the entity already exists)."
    UPDATE = "update", "maps to PATCH /v2/entities/<id>/attrs."
    DELETE = "delete", "maps to DELETE /v2/entities/<id>/attrs/<attrName> on " \
                       "every attribute included in the entity or to DELETE " \
                       "/v2/entities/<id> if no attribute were included in " \
                       "the entity."
    REPLACE = "replace", "maps to PUT /v2/entities/<id>/attrs"


class Update(BaseModel):
    """
    Model for update action
    """
    action_type: Union[ActionType, str] = Field(
        alias='actionType',
        description="actionType, to specify the kind of update action to do: "
                    "either append, appendStrict, update, delete, or replace. "
    )
    entities: List[ContextEntity] = Field(
        description="an array of entities, each entity specified using the "
                    "JSON entity representation format "
    )

    @validator('action_type')
    def check_action_type(cls, action):
        """
        validates action_type
        Args:
            action: field action_type
        Returns:
            action_type
        """
        return ActionType(action)


class Command(BaseModel):
    """
    Class for sending commands to IoT Devices.
    Note that the command must be registered via an IoT-Agent. Internally
    FIWARE uses its registration mechanism in order to connect the command
    with an IoT-Device
    """
    type: DataType = Field(default=DataType.COMMAND,
                           description="Command must have the type command",
                           const=True)
    value: Any = Field(description="Any json serializable command that will "
                                   "be forwarded to the connected IoT device")

    @validator("value")
    def check_value(cls, value):
        """
        Check if value is json serializable
        Args:
            value: value field
        Returns:
            value
        """
        json.dumps(value)
        return value


class NamedCommand(Command):
    """
    Class for sending command to IoT-Device.
    Extend :class: Command with command Name
    """
    name: str = Field(
        description="Name of the command",
        max_length=256,
        min_length=1,
        regex=FiwareRegex.string_protect.value
    )
