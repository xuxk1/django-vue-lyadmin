<template>
    <div v-dialogDrag>
        <el-dialog
                :title="loadingTitle"
                v-model="dialogVisible"
                width="560px"
                center
                :destroy-on-close="true"
                :close-on-click-modal="false"
                :before-close="handleClose">
            <el-form :inline="false" :model="formData" ref="rulesForm" label-position="right" label-width="130px">
                <el-form-item label="用户头像：">
                    <img :src="formData.avatar ? formData.avatar : defaultImg" style="width: 60px;height:60px" :onerror="defaultImg">

    <!--                <el-upload-->
    <!--                        class="avatar-uploader"-->
    <!--                        action=""-->
    <!--                        :show-file-list="false"-->
    <!--                        :http-request="imgUploadRequest"-->
    <!--                        :on-success="imgUploadSuccess"-->
    <!--                        :before-upload="imgBeforeUpload">-->
    <!--                    <img v-if="formData.img" :src="formData.img" class="avatar">-->
    <!--                    <i v-else class="el-icon-plus avatar-uploader-icon"></i>-->
    <!--                </el-upload>-->
                </el-form-item>
                <el-form-item label="用户名：" prop="username">
                    {{formData.username}}
                </el-form-item>
                <el-form-item label="用户昵称：" prop="nickname">
                    {{formData.nickname}}
                </el-form-item>
                <el-form-item label="手机号：" prop="mobile">
                    {{formData.mobile}}
                </el-form-item>
                <el-form-item label="所属部门：" prop="dept_name">
                    {{formData.dept_name || '未分配'}}
                </el-form-item>
                <el-form-item label="角色：" prop="role_names">
                    <el-tag v-for="(name, index) in formData.role_names" :key="index" size="small" style="margin-right: 5px">{{ name }}</el-tag>
                    <span v-if="!formData.role_names || formData.role_names.length === 0">未分配</span>
                </el-form-item>
                <el-form-item label="允许登录后台：" prop="is_staff">
                    <el-switch
                            v-model="formData.is_staff"
                            active-color="#13ce66"
                            inactive-color="#ff4949" disabled>
                    </el-switch>
                </el-form-item>
                <el-form-item label="创建时间：" prop="mobile">
                    {{formData.create_datetime}}
                </el-form-item>
                <el-form-item label="更新时间：" prop="mobile">
                    {{formData.update_datetime}}
                </el-form-item>
                <el-form-item label="状态：" prop="is_active">
                    <el-switch
                            v-model="formData.is_active"
                            active-color="#13ce66"
                            inactive-color="#ff4949" disabled>
                    </el-switch>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="handleClose" :loading="loadingSave">取消</el-button>
    <!--            <el-button type="primary" @click="submitData" :loading="loadingSave">确定</el-button>-->
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import {apiSystemUserAdd,apiSystemUserEdit,apiSystemRole,apiSystemDept} from "@/api/api";
    export default {
        name: "userDetail",
        emits: ['refreshData'],
        data() {
            return {
                dialogVisible:false,
                loadingSave:false,
                loadingTitle:'',
                defaultImg:'this.src="'+require('../../../assets/img/avatar.jpg')+'"',
                formData:{
                    name:'',
                    nickname:'',
                    username:'',
                    mobile:'',
                    create_datetime:'',
                    update_datetime:'',
                    is_active:true,
                    is_staff:false,
                    avatar:'',
                    dept_name: '',
                    role_names: []
                },
                rolelist:[],
                options:[],
            }
        },
        methods:{

            handleClose() {
                this.dialogVisible=false
                this.loadingSave=false
                this.$emit('refreshData')
            },
            addUserFn(item,flag) {
                this.loadingTitle=flag
                this.dialogVisible=true
                this.formData=item ? item : {
                    name:'',
                    nickname:'',
                    username:'',
                    mobile:'',
                    create_datetime:'',
                    update_datetime:'',
                    is_active:true,
                    is_staff:false,
                    avatar:'',
                    dept_name: '',
                    role_names: []
                }
            },
            submitData() {
                this.$refs['rulesForm'].validate(obj=>{
                    if(obj) {
                        this.loadingSave=true
                        let param = {
                            ...this.formData
                        }
                        if(this.formData.id){
                            apiSystemUserEdit(param).then(res=>{
                                this.loadingSave=false
                                if(res.code ==2000) {
                                    this.$message.success(res.msg)
                                    this.handleClose()
                                    this.$emit('refreshData')
                                } else {
                                    this.$message.warning(res.msg)
                                }
                            })
                        }else{
                            apiSystemUserAdd(param).then(res=>{
                                this.loadingSave=false
                                if(res.code ==2000) {
                                    this.$message.success(res.msg)
                                    this.handleClose()
                                    this.$emit('refreshData')
                                } else {
                                    this.$message.warning(res.msg)
                                }
                            })
                        }

                    }
                })
            },
            imgBeforeUpload(file) {
                const isJPG = file.type === 'image/jpeg' || file.type === 'image/png';
                if (!isJPG) {
                    this.$message.error('图片只能是 JPG/PNG 格式!');
                    return false
                }
                return isJPG;
            },
            async imgUploadRequest(option) {
                // OSS.ossUploadProductImg(option);
            },
            imgUploadSuccess(res) {
                if (res) {
                    this.formData.img = res.url
                }
            },
        }
    }
</script>

