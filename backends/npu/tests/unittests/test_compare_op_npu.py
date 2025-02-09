#  Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import unittest

import numpy as np
import paddle
import paddle.base as base
from paddle.base import Program, program_guard
from tests.op_test import OpTest, convert_float_to_uint16
from npu_utils import get_cann_version

CANN_VERSION_CODE = get_cann_version()


def create_test_class(op_type, typename, callback):
    class Cls(OpTest):
        def setUp(self):
            self.set_npu()
            self.place = paddle.CustomPlace("npu", 0)
            self.op_type = op_type

        def init_input_output(self, shape1, shape2):
            if typename == "bfloat16":
                x = np.random.random(size=shape1).astype(np.float32)
                y = np.random.random(size=shape2).astype(np.float32)
                self.inputs = {
                    "X": convert_float_to_uint16(x),
                    "Y": convert_float_to_uint16(y),
                }
            else:
                x = np.random.random(size=shape1).astype(typename)
                y = np.random.random(size=shape2).astype(typename)
                self.inputs = {"X": x, "Y": y}
            out = callback(x, y)
            self.outputs = {"Out": out}

        def set_npu(self):
            self.__class__.use_custom_device = True

        def test_output(self):
            self.init_input_output((10, 7), (10, 7))
            self.check_output_with_place(place=self.place)

        def test_output1(self):
            self.init_input_output((8192,), (8192,))
            self.check_output_with_place(place=self.place)

        def test_output2(self):
            self.init_input_output((2, 4096, 1), (2, 4096, 1))
            self.check_output_with_place(place=self.place)

        def test_errors(self):
            paddle.enable_static()
            with program_guard(Program(), Program()):
                a = paddle.static.data(name="a", shape=[-1, 2], dtype="float32")
                b = paddle.static.data(name="b", shape=[-1, 2], dtype="float32")
                c = paddle.static.data(name="c", shape=[-1, 2], dtype="int16")
                d = base.create_lod_tensor(np.array([[-1]]), [[1]], self.place)

                op = eval("paddle.%s" % self.op_type)
                self.assertRaises(TypeError, op, x=a, y=b, axis=True)
                self.assertRaises(TypeError, op, x=a, y=b, force_cpu=1)
                self.assertRaises(TypeError, op, x=a, y=b, cond=1)

                try:
                    result = op(x=a, y=c)
                except TypeError:
                    self.fail(
                        "TypeError should not raised for float32 and int16 inputs"
                    )

                try:
                    result = op(x=c, y=a)
                except TypeError:
                    self.fail(
                        "TypeError should not raised for int16 and float32 inputs"
                    )

                self.assertRaises(TypeError, op, x=a, y=d)
                self.assertRaises(TypeError, op, x=d, y=a)
                self.assertRaises(TypeError, op, x=c, y=d)

        def test_dynamic_api(self):
            paddle.disable_static()
            paddle.set_device("npu:0")
            if typename == "bfloat16":
                x = np.random.random(size=(10, 7)).astype(np.float32)
                y = np.random.random(size=(10, 7)).astype(np.float32)
            else:
                x = np.random.random(size=(10, 7)).astype(typename)
                y = np.random.random(size=(10, 7)).astype(typename)
            real_result = callback(x, y)
            x = paddle.to_tensor(x, dtype=typename)
            y = paddle.to_tensor(y, dtype=typename)
            op = eval("paddle.%s" % (self.op_type))
            out = op(x, y)
            self.assertEqual((out.numpy() == real_result).all(), True)

        def test_dynamic_api_different_type(self):
            if op_type != "equal":
                return
            paddle.disable_static()
            paddle.set_device("npu:0")
            y = np.random.random(size=(10, 7)).astype("int32")
            if typename == "bfloat16":
                x = np.random.random(size=(10, 7)).astype(np.float32)
            else:
                x = np.random.random(size=(10, 7)).astype(typename)
            real_result = callback(x, y)
            x = paddle.to_tensor(x, dtype=typename)
            y = paddle.to_tensor(y, dtype="float32")
            op = eval("paddle.%s" % (self.op_type))
            out = op(x, y)
            self.assertEqual((out.numpy() == real_result).all(), True)

        def test_broadcast_api_1(self):
            paddle.enable_static()
            with program_guard(Program(), Program()):
                x = paddle.static.data(name="x", shape=[1, 2, 1, 3], dtype=typename)
                y = paddle.static.data(name="y", shape=[1, 2, 3], dtype=typename)
                op = eval("paddle.%s" % (self.op_type))
                out = op(x, y)
                exe = paddle.static.Executor(self.place)
                if typename == "bfloat16":
                    input_x = np.arange(1, 7).reshape((1, 2, 1, 3)).astype(np.float32)
                    input_y = np.arange(0, 6).reshape((1, 2, 3)).astype(np.float32)
                    (res,) = exe.run(
                        feed={
                            "x": convert_float_to_uint16(input_x),
                            "y": convert_float_to_uint16(input_y),
                        },
                        fetch_list=[out],
                    )
                else:
                    input_x = np.arange(1, 7).reshape((1, 2, 1, 3)).astype(typename)
                    input_y = np.arange(0, 6).reshape((1, 2, 3)).astype(typename)
                    (res,) = exe.run(
                        feed={"x": input_x, "y": input_y}, fetch_list=[out]
                    )
                real_result = callback(input_x, input_y)
            self.assertEqual((res == real_result).all(), True)

        def test_broadcast_api_2(self):
            paddle.enable_static()
            with program_guard(Program(), Program()):
                x = paddle.static.data(name="x", shape=[1, 2, 3], dtype=typename)
                y = paddle.static.data(name="y", shape=[1, 2, 1, 3], dtype=typename)
                op = eval("paddle.%s" % (self.op_type))
                out = op(x, y)
                exe = paddle.static.Executor(self.place)
                if typename == "bfloat16":
                    input_x = np.arange(0, 6).reshape((1, 2, 3)).astype(np.float32)
                    input_y = np.arange(1, 7).reshape((1, 2, 1, 3)).astype(np.float32)
                    (res,) = exe.run(
                        feed={
                            "x": convert_float_to_uint16(input_x),
                            "y": convert_float_to_uint16(input_y),
                        },
                        fetch_list=[out],
                    )
                else:
                    input_x = np.arange(0, 6).reshape((1, 2, 3)).astype(typename)
                    input_y = np.arange(1, 7).reshape((1, 2, 1, 3)).astype(typename)
                    (res,) = exe.run(
                        feed={"x": input_x, "y": input_y}, fetch_list=[out]
                    )
                real_result = callback(input_x, input_y)
            self.assertEqual((res == real_result).all(), True)

        def test_broadcast_api_3(self):
            paddle.enable_static()
            with program_guard(Program(), Program()):
                x = paddle.static.data(name="x", shape=[5], dtype=typename)
                y = paddle.static.data(name="y", shape=[3, 1], dtype=typename)
                op = eval("paddle.%s" % (self.op_type))
                out = op(x, y)
                exe = paddle.static.Executor(self.place)
                if typename == "bfloat16":
                    input_x = np.arange(0, 5).reshape((5)).astype(np.float32)
                    input_y = np.array([5, 3, 2]).reshape((3, 1)).astype(np.float32)
                    (res,) = exe.run(
                        feed={
                            "x": convert_float_to_uint16(input_x),
                            "y": convert_float_to_uint16(input_y),
                        },
                        fetch_list=[out],
                    )
                else:
                    input_x = np.arange(0, 5).reshape((5)).astype(typename)
                    input_y = np.array([5, 3, 2]).reshape((3, 1)).astype(typename)
                    (res,) = exe.run(
                        feed={"x": input_x, "y": input_y}, fetch_list=[out]
                    )
                real_result = callback(input_x, input_y)
            self.assertEqual((res == real_result).all(), True)

        def test_attr_name(self):
            paddle.enable_static()
            with program_guard(Program(), Program()):
                x = paddle.static.data(name="x", shape=[-1, 4], dtype=typename)
                y = paddle.static.data(name="y", shape=[-1, 4], dtype=typename)
                op = eval("paddle.%s" % (self.op_type))
                out = op(x=x, y=y, name="name_%s" % (self.op_type))
            self.assertEqual("name_%s" % (self.op_type) in out.name, True)

    cls_name = "{0}_{1}".format(op_type, typename)
    Cls.__name__ = cls_name
    globals()[cls_name] = Cls


for _type_name in {"float16", "float32", "int32", "int64", "bool"}:
    create_test_class("equal", _type_name, lambda _a, _b: _a == _b)
    create_test_class("not_equal", _type_name, lambda _a, _b: _a != _b)
    create_test_class("less_than", _type_name, lambda _a, _b: _a < _b)
    create_test_class("less_equal", _type_name, lambda _a, _b: _a <= _b)
    create_test_class("greater_than", _type_name, lambda _a, _b: _a > _b)
    create_test_class("greater_equal", _type_name, lambda _a, _b: _a >= _b)


if CANN_VERSION_CODE >= 7:
    create_test_class("equal", "bfloat16", lambda _a, _b: _a == _b)
    create_test_class("not_equal", "bfloat16", lambda _a, _b: _a != _b)
    create_test_class("less_than", "bfloat16", lambda _a, _b: _a < _b)
    create_test_class("less_equal", "bfloat16", lambda _a, _b: _a <= _b)
    create_test_class("greater_than", "bfloat16", lambda _a, _b: _a > _b)
    create_test_class("greater_equal", "bfloat16", lambda _a, _b: _a >= _b)


if __name__ == "__main__":
    unittest.main()
